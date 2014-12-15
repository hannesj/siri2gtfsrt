#!/usr/bin/python

import transitfeed
import json
import gtfs_realtime_pb2
from google.protobuf import text_format
from flask import Flask
from flask import request, abort
from urllib2 import urlopen
import time
import datetime
import dateutil.parser
import pytz
import os

url = "http://data.itsfactory.fi/journeys/api/1/vehicle-activity"

feed = transitfeed.Loader(feed_path="tampere_gtfs_latest.zip", problems=transitfeed.ProblemReporter(None)).Load()

EPOCH = datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)

app = Flask(__name__)


@app.route('/')
def index():
    journeys_data = json.loads(urlopen(url).read().decode('utf-8'))
    if journeys_data['status'] != "success":
        abort(500)
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "1.0"
    msg.header.incrementality = msg.header.FULL_DATASET
    msg.header.timestamp = int(time.time())

    for i, vehicle in enumerate(journeys_data['body']):
        route_id = vehicle['monitoredVehicleJourney']['lineRef']
        if route_id not in feed.routes:
            app.logger.debug("No route for: " + str(vehicle))
            continue

        ent = msg.entity.add()
        ent.id = str(i)
        ent.trip_update.trip.route_id = route_id

        route = feed.GetRoute(route_id)

        for trip in route.trips:
            date = vehicle['monitoredVehicleJourney']['framedVehicleJourneyRef']['dateFrameRef'].replace("-","")
            if not trip.service_period.IsActiveOn(date):
                continue
            start_time = vehicle['monitoredVehicleJourney']['originAimedDepartureTime']
            start_time_seconds = int(start_time[:2])*60*60+int(start_time[2:4])*60
            if trip.GetStartTime() != start_time_seconds:
                continue
            assert isinstance(trip, transitfeed.Trip)
            stoptimes = trip.GetStopTimes()
            if stoptimes[0].stop_id != vehicle['monitoredVehicleJourney']['originShortName']:
                continue
            if stoptimes[-1].stop_id != vehicle['monitoredVehicleJourney']['destinationShortName']:
                continue

            ent.trip_update.trip.trip_id = trip.trip_id

        if not ent.trip_update.trip.trip_id:
            app.logger.debug("No trip for: " + str(vehicle))

        if 'onwardCalls' not in vehicle['monitoredVehicleJourney']:
            continue

        for call in vehicle['monitoredVehicleJourney']['onwardCalls']:
            stoptime = ent.trip_update.stop_time_update.add()
            stoptime.stop_id = call['stopPointRef'].rsplit('/',1)[1]
            arrival_time = (dateutil.parser.parse(call['expectedArrivalTime']) - EPOCH).total_seconds()
            stoptime.arrival.time = int(arrival_time)
            departure_time = (dateutil.parser.parse(call['expectedDepartureTime']) - EPOCH).total_seconds()
            stoptime.departure.time = int(departure_time)

    if 'debug' in request.args:
        return text_format.MessageToString(msg)
    else:
        return msg.SerializeToString()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.debug = True
    app.run(host='0.0.0.0', port=port, use_reloader=False)
