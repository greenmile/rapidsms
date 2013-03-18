from django.db.models import Q

from rapidsms.router.blocking import BlockingRouter
from rapidsms.router.db.tasks import receive_async, send_transmissions
from rapidsms.messages.incoming import IncomingMessage
from rapidsms.messages.outgoing import OutgoingMessage


class DatabaseRouter(BlockingRouter):

    def queue_message(self, direction, connections, text, fields=None):
        """Create Message and Transmission objects for messages."""
        from rapidsms.router.db.models import Message, Transmission
        kwargs = {'text': text, 'direction': direction}
        # save external_id in database
        if fields and 'external_id' in fields:
            kwargs['external_id'] = fields['external_id']
        dbm = Message.objects.create(**kwargs)
        transmissions = []
        for connection in connections:
            transmissions.append(Transmission(message=dbm, status='Q',
                                              connection=connection))
        Transmission.objects.bulk_create(transmissions)
        return dbm

    def new_incoming_message(self, connections, text, **kwargs):
        """Create and attach database message to message object."""
        msg = super(DatabaseRouter, self).new_incoming_message(connections,
                                                               text,
                                                               **kwargs)
        # save and attach database meessage to message object
        msg.dbm = self.queue_message("I", connections, text, **kwargs)
        # set id of message to the database message primary key
        msg.id = msg.dbm.pk
        return msg

    def receive_incoming(self, msg):
        """Queue message in DB for async inbound processing."""
        receive_async.delay(message_id=msg.id, fields=msg.fields)

    def group_transmissions(self, transmissions, batch_size=200):
        """Divide transmissions by backend and into manageable chunks."""
        start = 0
        end = batch_size
        # divide transmissions by backend
        backends = transmissions.values_list('connection__backend_id',
                                             flat=True)
        for backend_id in backends.distinct():
            q = Q(connection__backend_id=backend_id)
            # filter down based on this backend and order by ID
            transmissions = transmissions.filter(q).order_by('id')
            while True:
                # divide transmissions into chunks of specified size
                batch = transmissions[start:end]
                if not batch.exists():
                    # query returned no rows, so we've seen all transmissions
                    break
                yield backend_id, batch
                start = end
                end += batch_size

    def backend_preparation(self, msg):
        """Queue message in DB rather than passing directly to backends."""
        # create queued message and associated transmissions
        dbm = self.queue_message("O", msg.connections, msg.text)
        # mark message as processing
        dbm.status = "P"
        # set in_response_to db field if available
        if msg.in_response_to and hasattr(msg.in_response_to, 'dbm'):
            dbm.in_response_to = msg.in_response_to.dbm
        dbm.save()
        for backend_id, trans in self.group_transmissions(dbm.transmissions):
            transmission_ids = list(trans.values_list('pk', flat=True))
            send_transmissions.delay(backend_id=backend_id,
                                     message_id=dbm.pk,
                                     transmission_ids=transmission_ids)

    def create_message_from_dbm(self, dbm, fields={}, fetch_connections=True):
        from rapidsms.models import Connection
        if fetch_connections:
            ids = dbm.transmissions.values_list('connection_id', flat=True)
            connections = Connection.objects.filter(id__in=list(ids))
        else:
            connections = []
        kwargs = {'connections': connections, 'text': dbm.text, 'id_': dbm.pk}
        if dbm.in_response_to:
            response = self.recreate_rapidsms_message(dbm.in_response_to,
                                                      fetch_connections)
            kwargs['in_response_to'] = response
        class_ = {'I': IncomingMessage, 'O': OutgoingMessage}[dbm.direction]
        msg = class_(**kwargs)
        msg.dbm = dbm
        msg.fields = fields
        return msg