"""Tests for app.services.hubspot — check_existing_contacts (HubSpot dedup)."""
import pytest
from unittest.mock import patch, MagicMock

from app.services.hubspot import check_existing_contacts


class TestCheckExistingContacts:
    """Batch read from HubSpot to find which emails already exist."""

    @patch('app.services.hubspot.HUBSPOT_API_KEY', 'test-key')
    @patch('app.services.circuit_breaker.get_breaker')
    def test_returns_existing_emails(self, mock_breaker):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            'results': [
                {'properties': {'email': 'alice@example.com'}},
                {'properties': {'email': 'bob@example.com'}},
            ],
        }
        mock_breaker.return_value.call.return_value = mock_resp

        result = check_existing_contacts(['alice@example.com', 'bob@example.com', 'new@example.com'])

        assert result == {'alice@example.com', 'bob@example.com'}

    @patch('app.services.hubspot.HUBSPOT_API_KEY', 'test-key')
    @patch('app.services.circuit_breaker.get_breaker')
    def test_returns_empty_set_when_none_exist(self, mock_breaker):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {'results': []}
        mock_breaker.return_value.call.return_value = mock_resp

        result = check_existing_contacts(['new@example.com'])
        assert result == set()

    @patch('app.services.hubspot.HUBSPOT_API_KEY', None)
    def test_returns_empty_when_no_api_key(self):
        result = check_existing_contacts(['alice@example.com'])
        assert result == set()

    def test_returns_empty_for_empty_email_list(self):
        result = check_existing_contacts([])
        assert result == set()

    @patch('app.services.hubspot.HUBSPOT_API_KEY', 'test-key')
    @patch('app.services.circuit_breaker.get_breaker')
    def test_handles_207_partial_response(self, mock_breaker):
        mock_resp = MagicMock(status_code=207)
        mock_resp.json.return_value = {
            'results': [{'properties': {'email': 'found@example.com'}}],
            'errors': [{'message': 'Not found'}],
        }
        mock_breaker.return_value.call.return_value = mock_resp

        result = check_existing_contacts(['found@example.com', 'missing@example.com'])
        assert result == {'found@example.com'}

    @patch('app.services.hubspot.HUBSPOT_API_KEY', 'test-key')
    @patch('app.services.circuit_breaker.get_breaker')
    def test_handles_api_error_gracefully(self, mock_breaker):
        mock_resp = MagicMock(status_code=500)
        mock_resp.text = 'Internal Server Error'
        mock_breaker.return_value.call.return_value = mock_resp

        result = check_existing_contacts(['alice@example.com'])
        assert result == set()

    @patch('app.services.hubspot.HUBSPOT_API_KEY', 'test-key')
    @patch('app.services.circuit_breaker.get_breaker')
    def test_handles_exception_gracefully(self, mock_breaker):
        mock_breaker.return_value.call.side_effect = Exception('Connection refused')

        result = check_existing_contacts(['alice@example.com'])
        assert result == set()

    @patch('app.services.hubspot.HUBSPOT_API_KEY', 'test-key')
    @patch('app.services.circuit_breaker.get_breaker')
    def test_lowercases_returned_emails(self, mock_breaker):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            'results': [{'properties': {'email': 'Alice@Example.COM'}}],
        }
        mock_breaker.return_value.call.return_value = mock_resp

        result = check_existing_contacts(['alice@example.com'])
        assert 'alice@example.com' in result

    @patch('app.services.hubspot.HUBSPOT_API_KEY', 'test-key')
    @patch('app.services.circuit_breaker.get_breaker')
    def test_sends_correct_payload(self, mock_breaker):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {'results': []}
        mock_breaker.return_value.call.return_value = mock_resp

        check_existing_contacts(['a@b.com', 'c@d.com'])

        call_args = mock_breaker.return_value.call.call_args
        payload = call_args.kwargs['json']
        assert payload['idProperty'] == 'email'
        assert payload['properties'] == ['email']
        assert len(payload['inputs']) == 2
        assert {'id': 'a@b.com'} in payload['inputs']
        assert {'id': 'c@d.com'} in payload['inputs']

    @patch('app.services.hubspot.HUBSPOT_API_KEY', 'test-key')
    @patch('app.services.hubspot.time')
    @patch('app.services.circuit_breaker.get_breaker')
    def test_batches_over_100_emails(self, mock_breaker, mock_time):
        """Emails are sent in batches of 100 with sleep between."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {'results': []}
        mock_breaker.return_value.call.return_value = mock_resp

        emails = [f'user{i}@example.com' for i in range(150)]
        check_existing_contacts(emails)

        assert mock_breaker.return_value.call.call_count == 2
        # First batch: 100, second batch: 50
        first_payload = mock_breaker.return_value.call.call_args_list[0].kwargs['json']
        second_payload = mock_breaker.return_value.call.call_args_list[1].kwargs['json']
        assert len(first_payload['inputs']) == 100
        assert len(second_payload['inputs']) == 50
        mock_time.sleep.assert_called_once_with(0.1)
