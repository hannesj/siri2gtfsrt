#!/usr/bin/python

import transitfeed
import json
import gtfs_realtime_pb2
from google.protobuf import text_format
from flask import Flask
from flask import request
from urllib2 import urlopen
import os

url = "http://dev.hsl.fi/siriaccess/vm/json?operatorRef=HSL"

feed = transitfeed.Loader(feed_path="HSL.zip", load_stop_times=False, problems=transitfeed.ProblemReporter(None)).Load()

app = Flask(__name__)


@app.route('/')
def index():
    siri_data = json.loads(urlopen(url).read().decode('utf-8'))['Siri']
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "1.0"
    msg.header.incrementality = msg.header.FULL_DATASET
    msg.header.timestamp = int(siri_data['ServiceDelivery']['ResponseTimestamp']) / 1000

    for i, vehicle in enumerate(siri_data['ServiceDelivery']['VehicleMonitoringDelivery'][0]['VehicleActivity']):
        route_id = vehicle['MonitoredVehicleJourney']['LineRef']['value'][:5].strip()

        if route_id in ('1300', '1300V', '1300M'):
            continue # No other information than location for metros

        if 'Delay' not in vehicle['MonitoredVehicleJourney']:
            app.logger.debug("No delay for: " + str(vehicle))
            continue

        if route_id not in feed.routes:
            app.logger.debug("No route for: " + str(vehicle))
            continue

        ent = msg.entity.add()
        ent.id = str(i)
        ent.trip_update.trip.route_id = route_id

        route = feed.GetRoute(route_id)

        for trip in route.trips:
            date = vehicle['MonitoredVehicleJourney']['FramedVehicleJourneyRef']['DataFrameRef']['value'].replace("-","")
            if not trip.service_period.IsActiveOn(date):
                continue
            start_time = vehicle['MonitoredVehicleJourney']['FramedVehicleJourneyRef']['DatedVehicleJourneyRef']
            if trip.trip_id[-4:] != start_time:
                continue
            if trip.trip_id[-6:-5] != vehicle['MonitoredVehicleJourney']['DirectionRef']['value']:
                app.logger.debug("invalid direction for " + vehicle['MonitoredVehicleJourney']['DirectionRef']['value'])
                continue

            ent.trip_update.trip.trip_id = trip.trip_id

        if not ent.trip_update.trip.trip_id:
            app.logger.debug("No trip for: " + str(vehicle))

        stoptime = ent.trip_update.stop_time_update.add()
        stoptime.stop_sequence = 1  # TODO: Get real stop index
        stoptime.arrival.delay = vehicle['MonitoredVehicleJourney']['Delay']

    if 'debug' in request.args:
        return text_format.MessageToString(msg)
    else:
        return msg.SerializeToString()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.debug = True
    app.run(host='0.0.0.0', port=port, use_reloader=False)
