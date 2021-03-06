from flask import Blueprint, render_template, request, flash, redirect, url_for
import psycopg2
import psycopg2.extras
import getpass
import uuid
from website.database.get_data import get_data
from website.database.input_update_records import insert_into_metadata_catalogue, update_record_metadata_catalogue
from website.database.harvest_activities import harvest_activities, get_bottom_depth
from website.database.checker import checker
import website.database.fields as fields
from website.other_functions.other_functions import distanceCoordinates, split_personnel_list
from . import DBNAME, CRUISE_NUMBER, METADATA_CATALOGUE, CRUISE_DETAILS_TABLE, VESSEL_NAME, TOKTLOGGER
import requests
import numpy as np
from datetime import datetime as dt

logsamples = Blueprint('logsamples', __name__)

@logsamples.route('/editActivity/<eventID>', methods=['GET', 'POST'])
def edit_activity_page(eventID):

    activity_fields = {
    'id': 'optional',
    'catalogNumber': 'optional',
    'stationName': 'required',
    'gearType': 'required',
    'eventDate': 'required',
    'eventTime': 'required',
    'endDate': 'optional',
    'endTime': 'optional',
    'decimalLatitude': 'required',
    'decimalLongitude': 'required',
    'endDecimalLatitude': 'optional',
    'endDecimalLongitude': 'optional',
    'minimumDepthInMeters': 'optional',
    'maximumDepthInMeters': 'optional',
    'minimumElevationInMeters': 'optional',
    'maximumElevationInMeters': 'optional',
    'pi_name': 'required',
    'pi_email': 'required',
    'recordedBy_name': 'required',
    'recordedBy_email': 'required',
    'samplingProtocolDoc': 'optional',
    'samplingProtocolSection': 'optional',
    'samplingProtocolVersion': 'optional',
    'comments1': 'optional',
    }

    df_personnel = get_data(DBNAME, 'personnel')
    df_personnel.sort_values(by='last_name', inplace=True)
    df_personnel['personnel'] = df_personnel['first_name'] + ' ' + df_personnel['last_name'] + ' (' + df_personnel['email'] + ')'
    personnel = list(df_personnel['personnel'])

    df_gears = get_data(DBNAME, 'gear_types')
    df_gears.sort_values(by='geartype', inplace=True)
    gearTypes = list(df_gears['geartype'])

    df_stations = get_data(DBNAME, 'stations')
    df_stations.sort_values(by='stationname', inplace=True)
    stationNames = list(df_stations['stationname'])

    df_metadata_catalogue = get_data(DBNAME, METADATA_CATALOGUE)

    activity_metadata = {}


    for field in fields.fields:
        if field['name'] in activity_fields.keys():
            activity_metadata[field['name']] = {}
            activity_metadata[field['name']]['disp_name'] = field['disp_name']
            activity_metadata[field['name']]['description'] = field['description']
            activity_metadata[field['name']]['format'] = field['format']
            if activity_fields[field['name']] == 'required':
                activity_metadata[field['name']]['required'] = True
            else:
                activity_metadata[field['name']]['required'] = False
            if eventID == 'addNew':
                if field['format'] in ['double precision', 'date', 'time']:
                    activity_metadata[field['name']]['value'] = None
                else:
                    activity_metadata[field['name']]['value'] = ''
            else:
                print('HERE', field['name'], ': ', df_metadata_catalogue.loc[df_metadata_catalogue['id'] == eventID, field['name'].lower()].iloc[0])
                activity_metadata[field['name']]['value'] = df_metadata_catalogue.loc[df_metadata_catalogue['id'] == eventID, field['name'].lower()].iloc[0]

    if activity_metadata['pi_name']['value'] != '':
        pi_names = activity_metadata['pi_name']['value'].split(' | ')
        pi_emails = activity_metadata['pi_email']['value'].split(' | ')
        pis = [f"{name} ({email})" for (name, email) in zip(pi_names, pi_emails)]
    else:
        pis = []

    if activity_metadata['recordedBy_name']['value'] != '':
        recordedBy_names = activity_metadata['recordedBy_name']['value'].split(' | ')
        recordedBy_emails = activity_metadata['recordedBy_email']['value'].split(' | ')
        recordedBys = [f"{name} ({email})" for (name, email) in zip(recordedBy_names, recordedBy_emails)]
    else:
        recordedBys = []

    activity_metadata['pi'] = {
        'disp_name': 'PI(s)',
        'description': 'Principal investigator for the sample or event',
        'format': 'text',
        'required': True,
        'value': pis
        }

    activity_metadata['recordedBy'] = {
        'disp_name': 'Recorded By',
        'description': 'The person(s) responsible for recording the original event or sample.',
        'format': 'text',
        'required': True,
        'value': recordedBys
        }

    fields_to_remove = ['pi_name', 'pi_email', 'recordedBy_name', 'recordedBy_email']
    for f in fields_to_remove:
        activity_metadata.pop(f)

    if request.method == 'POST':
        form_input = request.form.to_dict(flat=False)

        for key, value in form_input.items():
            if len(value) == 1 and key not in ['pis', 'recordedBys']:
                form_input[key] = value[0]
            elif len(value) == 0:
                form_input[key] = ''

        errors = checker(form_input, DBNAME, METADATA_CATALOGUE)

        print('ERRORS RETURNED:', errors, len(errors))
        if len(errors) > 0:
            for error in errors:
                flash(error, category='error')
        else:
            form_input['pi_name'], form_input['pi_email'], form_input['pi_institution'] = split_personnel_list(form_input['pis'], df_personnel)
            form_input['recordedBy_name'], form_input['recordedBy_email'], form_input['recordedBy_institution'] = split_personnel_list(form_input['recordedBys'], df_personnel)

            for field in fields.fields:
                if field['name'] in activity_fields.keys():
                    if form_input[field['name']] == '':
                        if field['format'] in ['int', 'double precision', 'time', 'date']:
                            form_input[field['name']] = 'NULL'
                        elif field['name'] == 'id':
                            form_input[field['name']] = str(uuid.uuid1())

            if eventID == 'addNew':

                form_input['created'] = dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                form_input['modified'] = dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                form_input['history'] = dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ Record created manually from add activity page")
                form_input['source'] = "Record created manually from add activity page"

                insert_into_metadata_catalogue(form_input, DBNAME, METADATA_CATALOGUE)

                flash('Activity registered!', category='success')

            else:

                form_input['history'] = df_metadata_catalogue.loc[df_metadata_catalogue['id'] == eventID, 'history'].iloc[0]
                form_input['history'] = form_input['history'] + '\n' + dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ Record modified using edit activity page")
                form_input['modified'] = dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

                update_record_metadata_catalogue(form_input, DBNAME, METADATA_CATALOGUE)

                flash('Activity edited!', category='success')

            # return redirect(url_for('logsamples.home'))

    if eventID == 'addNew':
        eventID = ''

    return render_template(
    "addActivity.html",
    personnel=personnel,
    gearTypes=gearTypes,
    stationNames=stationNames,
    eventID=eventID,
    activity_metadata=activity_metadata,
    pis=pis,
    recordedBys=recordedBys
    )
