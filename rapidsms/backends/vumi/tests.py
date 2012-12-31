from django.test import TestCase
from django.core.urlresolvers import reverse
from django.conf.urls.defaults import *
from django.utils import simplejson as json

from rapidsms.backends.vumi import views
from rapidsms.backends.vumi.outgoing import VumiBackend
from rapidsms.backends.vumi.forms import VumiForm
from rapidsms.tests.harness import RapidTest, CreateDataMixin


urlpatterns = patterns('',
    url(r"^backend/vumi/$",
        views.VumiBackendView.as_view(backend_name='vumi-backend'),
        name='vumi-backend'),
)


class VumiFormTest(TestCase):

    def setUp(self):
        self.valid_data = {"transport_name": "transport",
            "in_reply_to": None,
            "group": None,
            "from_addr": "127.0.0.1:38634",
            "message_type": "user_message",
            "helper_metadata": {},
            "to_addr": "0.0.0.0:8005",
            "content": "ping",
            "message_version": "20110921",
            "transport_type": "telnet",
            "timestamp": "2012-07-06 14:08:20.845715",
            "transport_metadata": {},
            "session_event": "resume",
            "message_id": "56047985ceec40da908ca064f2fd59d3"
        }

    def test_valid_form(self):
        """Form should be valid if GET keys match configuration."""
        form = VumiForm(self.valid_data, backend_name='vumi-backend')
        self.assertTrue(form.is_valid())

    def test_invalid_form(self):
        """Form is invalid if POST keys don't match configuration."""
        data = {'invalid-phone': '1112223333', 'invalid-message': 'hi there'}
        form = VumiForm(data, backend_name='vumi-backend')
        self.assertFalse(form.is_valid())

    def test_get_incoming_data(self):
        """get_incoming_data should return matching text and connection."""
        form = VumiForm(self.valid_data, backend_name='vumi-backend')
        form.is_valid()
        incoming_data = form.get_incoming_data()
        self.assertEqual(self.valid_data['content'], incoming_data['text'])
        self.assertEqual(self.valid_data['from_addr'],
                         incoming_data['connection'].identity)
        self.assertEqual('vumi-backend',
                         incoming_data['connection'].backend.name)


class VumiViewTest(RapidTest):

    urls = 'rapidsms.backends.vumi.tests'
    disable_phases = True

    def setUp(self):
        self.valid_data = {"transport_name": "transport",
            "in_reply_to": None,
            "group": None,
            "from_addr": "127.0.0.1:38634",
            "message_type": "user_message",
            "helper_metadata": {},
            "to_addr": "0.0.0.0:8005",
            "content": "ping",
            "message_version": "20110921",
            "transport_type": "telnet",
            "timestamp": "2012-07-06 14:08:20.845715",
            "transport_metadata": {},
            "session_event": "resume",
            "message_id": "56047985ceec40da908ca064f2fd59d3"
        }

    def test_valid_response_post(self):
        """HTTP 200 should return if data is valid."""
        response = self.client.post(reverse('vumi-backend'),
                                    json.dumps(self.valid_data),
                                    content_type='text/json')
        self.assertEqual(response.status_code, 200)

    def test_invalid_response(self):
        """HTTP 400 should return if data is invalid."""
        data = {'invalid-phone': '1112223333', 'message': 'hi there'}
        response = self.client.post(reverse('vumi-backend'), json.dumps(data),
                                    content_type='text/json')
        self.assertEqual(response.status_code, 400)

    def test_valid_post_message(self):
        """Valid POSTs should pass message object to router."""
        self.client.post(reverse('vumi-backend'), json.dumps(self.valid_data),
                         content_type='text/json')
        message = self.inbound[0]
        self.assertEqual(self.valid_data['content'], message.text)
        self.assertEqual(self.valid_data['from_addr'],
                         message.connection.identity)
        self.assertEqual('vumi-backend',
                         message.connection.backend.name)


class VumiSendTest(CreateDataMixin, TestCase):

    def test_required_fields(self):
        """Vumi backend requires Gateway URL and credentials."""
        self.assertRaises(TypeError, VumiBackend, None, "vumi")

    def test_outgoing_keys(self):
        """ Vumi requires JSON to include to_adr and content """
        message = self.create_outgoing_message()
        config = {
            "vumi_url": "http://example.com",
            "vumi_credentials": {'username': 'user', 'password': 'pass'},
        }
        backend = VumiBackend(None, "kannel", **config)
        request = backend._build_request(message)
        self.assertEqual(request.get_full_url(), "http://example.com")
        self.assertTrue('to_addr' in request.get_data())
        self.assertTrue('content' in request.get_data())