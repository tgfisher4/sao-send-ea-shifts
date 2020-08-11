#! /usr/bin/env python3
from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from pprint import pprint
from itertools import dropwhile, takewhile
import re
from datetime import date
import calendar
from more_itertools import nth
from sys import argv

''' Helpful globals for easy access'''
# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

EA_SPREADSHEET_ID   = '1LemZzn9txszU_KJvwrJk3ZbnwXxn8HLQBl8Cf90LrGs'
EA_EVENTS_RANGE     = 'Events!A2:I'
EVENT_COLUMN_NAMES = ['event_name', 'location', 'date', 'event_time', 'report_time', 'num_EAs', 'meeting_point', 'notes', 'group']
EVENT_COLUMN_IDXS  = {col: idx for idx, col in enumerate(EVENT_COLUMN_NAMES)}
DEFAULT_GROUP       = '2'
EA_SCHED_RANGE      = 'EA / Events!A2:C'
SCHED_COLUMN_NAMES  = ['event_name', 'date', 'EAs']
SCHED_COLUMN_IDXS   = {col: idx for idx, col in enumerate(SCHED_COLUMN_NAMES)}



def usage(ret_code=0):
    print('\n'.join(f'''
usage: {argv[0]} [options]

options:
    -g <group_num>              Send reminder message for the next events in the spreadsheet for group <group_num>
    -m <custom_message>         Include <custom_message> in message greeting
        '''.split('\n')[1:-1]))
    exit(ret_code)

def get_sheets_API_obj():
    # copied from pre-packaged example

    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('sheets', 'v4', credentials=creds)
    sheets_API_obj = service.spreadsheets()

    return sheets_API_obj

def get_events(sheet):
    ''' isolate impure functionality '''
    results = sheet.values().get(spreadsheetId=EA_SPREADSHEET_ID,
                                range=EA_EVENTS_RANGE).execute()
    values = results.get('values', [])

    if not values:
        print("error: no event data found")
        return None

    return values

def get_schedule(sheet):
    ''' isolate impure functionality '''
    results = sheet.values().get(spreadsheetId=EA_SPREADSHEET_ID,
                                range=EA_SCHED_RANGE).execute()
    values = results.get('values', [])

    if not values:
        print("error: no scedule data found")
        return None

    return values

def get_next_events(events, group, column_idxs=EVENT_COLUMN_IDXS):
    today = date.today()
    
    next_group_events = takewhile(lambda e: len(e) >= column_idxs['group']+1 and e[column_idxs['group']] == group, # finally, take entire event chunk for group
                                  dropwhile(lambda e: len(e) < column_idxs['group']+1 or e[column_idxs['group']] != group, # next, drop events that don't belong to group
                                            dropwhile(lambda e: date_str_to_obj(e[column_idxs['date']]) < today, # first, drop past events
                                                      events)))
    return next_group_events

def message_from_events(events, schedule, custom_message, column_idxs=EVENT_COLUMN_IDXS):
    preface = f'Hey guys! {custom_message}{" " if custom_message else ""}Here are our shifts for'

    events_list = list(events) # for some reason, calling list on my iterator caused it to be consumed so I needed to save the list
    message = f'{preface} {day_of_event(first(events_list))}:\n\n' + '\n\n'.join(map(lambda e: event_to_str(e, schedule), events_list))

    return message

def day_of_event(event, column_idxs=EVENT_COLUMN_IDXS):
    day_regex  = re.compile(r'^(?P<day_info>.*), \d{4}$')
    day_pieces = day_regex.match(event[column_idxs['date']])
    return day_pieces['day_info']

def event_to_str(event, schedule, column_idxs=EVENT_COLUMN_IDXS):
    rem_EAs = int(event[column_idxs['num_EAs']]) - num_EAs_scheduled(event[column_idxs['event_name']], schedule) if event[column_idxs['num_EAs']] else '?'
    return f'  {event[column_idxs["event_name"]]} - {event[column_idxs["location"]]}: {rem_EAs} EA{"" if rem_EAs != "?" and int(rem_EAs) == 1 else "s"} {clean_time_str(event[column_idxs["report_time"]] or event[column_idxs["event_time"]])}'

def clean_time_str(time_str):
    time_regex  = re.compile(r'(?P<start_hr>\d{1,2})(?P<start_colon>:)?(?(start_colon)(?P<start_min>\d{2}))(?P<start_m>pm|PM|AM|am)?\s?-\s?(?P<end_hr>\d{1,2})(?P<end_colon>:)?(?(end_colon)(?P<end_min>\d{2}))(?P<end_m>pm|PM|AM|am)')
    time_pieces = time_regex.match(time_str).groupdict()

    clean_time  = f'{time_pieces["start_hr"]}:{time_pieces["start_min"] or "00"}{(time_pieces["start_m"] and time_pieces["start_m"].lower()) or time_pieces["end_m"].lower()} - {time_pieces["end_hr"]}:{time_pieces["end_min"] or "00"}{time_pieces["end_m"].lower()}'

    return clean_time

def first(iterable):
    return nth(iterable, 0)
        
def date_str_to_obj(date_str):
    date_regex = re.compile(r'\w+, (?P<month>\w+) (?P<day>\d{1,2}), (?P<year>\d{4})')
    date_regex = re.compile(r'\w+, (?P<month>\w+) (?P<day>\d{1,2}), (?P<year>\d{4})')

    date_pieces = date_regex.search(date_str).groupdict()
    return date(int(date_pieces['year']), list(calendar.month_name).index(date_pieces['month']), int(date_pieces['day']))

def num_EAs_scheduled(event_name, schedule, column_idxs=SCHED_COLUMN_IDXS):
    event_sched = first(filter(lambda e: e[column_idxs['event_name']] == event_name, schedule))
    return len(event_sched[column_idxs['EAs']].split(',')) if len(event_sched) >= column_idxs['EAs'] + 1 else 0

def process_args():
    to_return = {}
    to_process = iter(argv[1:])
    for arg in to_process:
        if arg == '-g':
            to_return['group'] = next(to_process)
        elif arg == '-m':
            to_return['message'] = next(to_process)
        elif arg in ['-h', '--help']:
            usage(0)
        else:
            usage(1)
    return to_return

def main():
    """Shows basic usage of the Sheets API.
    Prints values from a sample spreadsheet.
    """
    
    arg_dict = process_args()
    group = arg_dict.get('group', DEFAULT_GROUP)
    custom_message = arg_dict.get('message', '')

    sheets_API_obj = get_sheets_API_obj()
    
    next_events = list(get_next_events(get_events(sheets_API_obj), group))

    if next_events:
        print(message_from_events(next_events, get_schedule(sheets_API_obj), custom_message))
    else:
        print("No upcoming events")


if __name__ == '__main__':
    main()