from __future__ import absolute_import
import time
import argparse
import json
from google.cloud import logging

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.options.pipeline_options import SetupOptions
import requests

from settings import PROJECT_ID, REGION, BUCKET_NAME, JOB_NAME, RUNNER, INCOMING_PUBSUB_SUBSCRIPTION, OUTGOING_PUBSUB_TOPIC, AQ_API_KEY

aq_baseurl = 'http://api.airvisual.com/v2/city'

version = {}
with open("./version.py") as fp:
    exec(fp.read(), version)


class GetAirQuality(beam.DoFn):
    def process(self, element):
        decoded_data = element.data.decode("utf-8")
        data = json.loads(decoded_data)

        api_url = f"{aq_baseurl}?city=Boston&state=Massachusetts&country=USA&key={AQ_API_KEY}"
        r = requests.get(api_url)

        aq_dict = r.json()
        air_q = data['air_quality']
        air_q.append(aq_dict)
        data['air_quality'] = air_q
        currentTime = time.time()
        data['ne_arrival'] = currentTime
        enriched_bird_str = json.dumps(data).encode('utf-8')
        updated_element = element
        updated_element.data = enriched_bird_str


        client = logging.Client()
        log_name = data['uuid']
        logger = client.logger(log_name)

        logger.log_text(f"NORTHEAST, v.{version['__version__']}, uuid: {data['uuid']}, Elapsed time since last step: {currentTime - data['start_time']}")
        yield updated_element


def run(argv=None, save_main_session=True):
    """Build and run the pipeline."""
    parser = argparse.ArgumentParser()
    known_args, pipeline_args = parser.parse_known_args(argv)
    pipeline_args.extend([
        f'--runner={RUNNER}',
        f'--project={PROJECT_ID}',
        f'--region={REGION}',
        f'--staging_location=gs://{BUCKET_NAME}/staging',
        f'--temp_location=gs://{BUCKET_NAME}/temp',
        f'--job_name={JOB_NAME}',
        '--setup_file="./setup.py"',
        '--streaming'
    ])

    pipeline_options = PipelineOptions(pipeline_args)
    pipeline_options.view_as(SetupOptions).save_main_session = save_main_session


    with beam.Pipeline(options=pipeline_options) as p:

        incoming_birds = p | 'Read Messages From start_migration PubSub' >> beam.io.ReadFromPubSub(
            subscription=f"projects/{PROJECT_ID}/subscriptions/{INCOMING_PUBSUB_SUBSCRIPTION}",
            with_attributes=True)

        enriched_birds = incoming_birds | 'Get air quality data' >> beam.ParDo(GetAirQuality())

        enriched_birds | "Write to depart_ne PubSub" >> beam.io.WriteToPubSub(topic=f"projects/{PROJECT_ID}/topics/{OUTGOING_PUBSUB_TOPIC}",with_attributes=True)


if __name__ == '__main__':
    print('go!')
    run()
