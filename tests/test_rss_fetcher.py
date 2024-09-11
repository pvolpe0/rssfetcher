import unittest
from unittest.mock import patch, mock_open, MagicMock
from datetime import datetime, timezone
import json
import yaml
import rss_fetcher

class TestRSSFetcher(unittest.TestCase):

    @patch('rss_fetcher.open', new_callable=mock_open, read_data=yaml.dump({
        'rss_feed_routes': ['route1', 'route2'],
        'rsshub_base_url': 'example.com',
        'sqs_queue_name': 'test_queue',
        'aws_region': 'us-east-1'
    }))
    def test_load_config(self, mock_open):
        config = rss_fetcher.load_config()
        expected_config = {
            'rss_feed_routes': ['route1', 'route2'],
            'rsshub_base_url': 'example.com',
            'sqs_queue_name': 'test_queue',
            'aws_region': 'us-east-1'
        }
        self.assertEqual(config, expected_config)

    @patch('requests.get')
    def test_fetch_rss_feed(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200,
                                          text='<rss><item><link>http://example.com</link></item></rss>')
        feed_data = rss_fetcher.fetch_rss_feed('http://example.com/rss')
        self.assertIn('<item><link>http://example.com</link></item>', feed_data)

    def test_process_feed(self):
        feed_data = '''
        <rss>
            <item>
                <link>http://example.com/article1</link>
                <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
                <category>Tech</category>
            </item>
            <item>
                <link>http://example.com/article2</link>
                <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
            </item>
        </rss>
        '''
        start_datetime = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_datetime = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        articles = rss_fetcher.process_feed(feed_data, start_datetime, end_datetime)
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]['url'], 'http://example.com/article1')
        self.assertEqual(articles[0]['tags'], ['Tech'])

    def test_serialize_message(self):
        message = {
            'url': 'http://example.com/article1',
            'pub_date': datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            'tags': ['Tech']
        }
        serialized_message = rss_fetcher.serialize_message(message)
        self.assertEqual(serialized_message['pub_date'], '2024-01-01T00:00:00+00:00')

    @patch('boto3.client')
    def test_send_to_sqs(self, mock_boto_client):
        mock_sqs = MagicMock()
        mock_boto_client.return_value = mock_sqs
        messages = [{'url': 'http://example.com/article1', 'pub_date': '2024-01-01T00:00:00+00:00', 'tags': ['Tech']}]
        rss_fetcher.send_to_sqs('test_queue', 'us-east-1', messages)
        self.assertEqual(mock_sqs.send_message.call_count, 1)
        args, kwargs = mock_sqs.send_message.call_args
        self.assertIn('MessageBody', kwargs)
        self.assertEqual(json.loads(kwargs['MessageBody'])['url'], 'http://example.com/article1')

    @patch('rss_fetcher.load_config')
    @patch('rss_fetcher.fetch_rss_feed')
    @patch('rss_fetcher.process_feed')
    @patch('rss_fetcher.send_to_sqs')
    def test_main(self, mock_send_to_sqs, mock_process_feed, mock_fetch_rss_feed, mock_load_config):
        mock_load_config.return_value = {
            'rss_feed_routes': ['route1'],
            'rsshub_base_url': 'example.com',
            'sqs_queue_name': 'test_queue',
            'aws_region': 'us-east-1'
        }
        mock_fetch_rss_feed.return_value = '<rss><item><link>http://example.com</link></item></rss>'
        mock_process_feed.return_value = [
            {'url': 'http://example.com', 'pub_date': '2024-01-01T00:00:00+00:00', 'tags': []}]

        with patch('sys.argv', ['rss_fetcher.py', '2024-01-01T00:00:00+00:00', '2024-01-02T00:00:00+00:00']):
            rss_fetcher.main('2024-01-01T00:00:00+00:00', '2024-01-02T00:00:00+00:00')

        mock_load_config.assert_called_once()
        mock_fetch_rss_feed.assert_called_once_with('http://example.com/route1')
        mock_process_feed.assert_called_once()
        mock_send_to_sqs.assert_called_once()


if __name__ == '__main__':
    unittest.main()
