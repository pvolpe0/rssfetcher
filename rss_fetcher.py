# rss_fetcher.py
import requests
import boto3
import json
import yaml
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import sys


def load_config():
    with open('config/config.yaml', 'r') as file:
        return yaml.safe_load(file)

def fetch_rss_feed(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.text  # Assuming RSSHub returns XML or JSON

def process_feed(feed_data, start_datetime, end_datetime):
    # Ensure start_datetime and end_datetime are timezone-aware (UTC)
    if start_datetime.tzinfo is None:
        start_datetime = start_datetime.replace(tzinfo=timezone.utc)  # Use Python's built-in timezone
    if end_datetime.tzinfo is None:
        end_datetime = end_datetime.replace(tzinfo=timezone.utc)

    # Parse the XML feed data with BeautifulSoup
    soup = BeautifulSoup(feed_data, 'xml')
    articles = []

    # Find all <item> elements in the RSS feed (or <entry> for Atom feeds)
    for item in soup.find_all('item'):  # Use 'entry' for Atom feeds
        article = {}

        # Extract the URL from the <link> element
        link = item.find('link')
        if link is not None:
            article['url'] = link.text.strip()

        # Extract the publication date from the <pubDate> element
        pub_date = item.find('pubDate')
        if pub_date is not None:
            pub_date_str = pub_date.text.strip()
            try:

                # Replace 'GMT' with '+0000' for compatibility
                pub_date_str = pub_date_str.replace('GMT', '+0000')

                # Parse the pubDate into a datetime object (RFC-822 format)
                pub_datetime = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z")
                article['pub_date'] = pub_datetime

                # Filter out articles outside the specified date range
                if not (start_datetime <= pub_datetime <= end_datetime):
                    continue
            except ValueError:
                # If the date can't be parsed, skip this article
                continue

        # Extract tags from <category> elements (if present)
        tags = item.find_all('category')
        article['tags'] = [tag.text.strip() for tag in tags if tag is not None]

        # Add the article to the list if it meets the criteria
        articles.append(article)

    return articles


def serialize_message(message):
    # Convert datetime objects to ISO 8601 string format
    if 'pub_date' in message and isinstance(message['pub_date'], datetime):
        message['pub_date'] = message['pub_date'].isoformat()

    return message

def send_to_sqs(queue_name, region, messages):
    sqs = boto3.client('sqs', region_name=region)
    queue_url = sqs.get_queue_url(QueueName=queue_name)['QueueUrl']
    for message in messages:
        # Convert each message to a serializable format
        serialized_message = serialize_message(message)
        sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(serialized_message))


def main(start_datetime_str, end_datetime_str):

    config = load_config()
    start_datetime = datetime.fromisoformat(start_datetime_str)
    end_datetime = datetime.fromisoformat(end_datetime_str)
    all_messages = []

    for route in config['rss_feed_routes']:
        feed_url = f"http://{config['rsshub_base_url']}/{route}"
        feed_data = fetch_rss_feed(feed_url)
        articles = process_feed(feed_data, start_datetime, end_datetime)
        all_messages.extend(articles)

    send_to_sqs(config['sqs_queue_name'], config['aws_region'], all_messages)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python rss_fetcher.py <start_datetime> <end_datetime>s")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
