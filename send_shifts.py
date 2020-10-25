#! /usr/bin/env python3
#from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from pprint import pprint
from itertools import dropwhile, takewhile
import re
from datetime import date, time, datetime, timedelta
import calendar
#from more_itertools import nth
from sys import argv
from copy import copy
from functools import reduce

''' Helpful globals for easy access'''
# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

#TEST_SPREADSHEET_ID = '1kPOfF-8sRcpXUTZv8K15ZaWRg9dZjLQv9VPyMk_2Obk'
TEST_SPREADSHEET_ID = '1SCquG08xYxvSMSARuM_3AfGGxdxh53DGAcWIHfcvKBc'
EA_SPREADSHEET_ID   = '1LemZzn9txszU_KJvwrJk3ZbnwXxn8HLQBl8Cf90LrGs'
EA_EVENTS_RANGE     = 'Events!A2:J'
EVENT_COLUMN_NAMES  = ['event_name', 'location', 'date', 'event_time', 'report_time', 'num_EAs', 'meeting_point', 'notes', 'group', 'EAs']
EVENT_COLUMN_IDXS   = {col: idx for idx, col in enumerate(EVENT_COLUMN_NAMES)}
DEFAULT_GROUP       = '2'
#EA_SCHED_RANGE      = 'EA / Events!A2:C'
#SCHED_COLUMN_NAMES  = ['event_name', 'date', 'EAs']
EVENT_NAME_COLUMN   = 'Events!A2:A'
EA_SCHED_COLUMN     = 'Events!J2:J'
SCHED_COLUMN_NAMES  = ['event_name', 'date', 'EAs']
SCHED_COLUMN_IDXS   = {col: idx for idx, col in enumerate(SCHED_COLUMN_NAMES)}

# next steps:
#   - connect with GroupMe API
#   - allow -d flag to search a specific date

def usage(ret_code=0):
    print('\n'.join(f'''
usage: {argv[0]} [options]

Prints to stdout a GroupMe message requesting EAs for a group's next events.

options:
    -g <group_num>              Generate message for group <group_num>'s next events
    -n                          Generate message for a request after the first (pneumonic: not first)
    -m <custom_message>         Include <custom_message> in message greeting
    -t                          Use testing spreadsheet instead of live SAO EA request spreadsheet
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

def get_events(sheet, use_test_sheet):
    ''' isolate impure functionality '''

    sheet_to_use = EA_SPREADSHEET_ID if not use_test_sheet else TEST_SPREADSHEET_ID
    results = sheet.values().get(spreadsheetId=sheet_to_use,
                                range=EA_EVENTS_RANGE).execute()
    values = results.get('values', [])

    if not values:
        print("error: no event data found")
        return None


    return values

def get_schedule(sheet, use_test_sheet):
    ''' isolate impure functionality '''
    sheet_to_use = EA_SPREADSHEET_ID if not use_test_sheet else TEST_SPREADSHEET_ID
    EA_results = sheet.values().get(spreadsheetId=sheet_to_use,
                                range=EA_SCHED_COLUMN).execute()
    EA_values = results.get('values', [])

    if not EA_values:
        print("error: no schedule data found")
        return None
    # hacky solution to get the script running after schedule tracking change
    event_results = sheet.values().get(spreadsheetId=sheet_to_use,
                                range=EVENT_NAME_COLUMN).execute()
    event_values = results.get('values', [])

    if not event_values:
        print("error: no event names found")
        return None
    
    to_return = zip(EA_values, event_values) #[ (event[EVENT_COLUMN_IDXS['event_name']], event[EVENT_COLUMN_IDXS['EAs']]) for event in values ]
    

    return to_return

def get_next_events(events, group, column_idxs=EVENT_COLUMN_IDXS):
    today = date.today()
    
    next_group_events = takewhile(lambda e: len(e) >= column_idxs['group']+1 and e[column_idxs['group']] == group, # finally, take entire event chunk for group
                                  dropwhile(lambda e: len(e) < column_idxs['group']+1 or e[column_idxs['group']] != group, # next, drop events that don't belong to group
                                            dropwhile(lambda e: date_str_to_obj(e[column_idxs['date']]) < today, # first, drop past events
                                                      events)))
    return next_group_events

def message_from_events(events, schedule, message, is_first_req, column_idxs=EVENT_COLUMN_IDXS):
    events_list = list(events)
    preface = f'{message or "Hey guys!"} {"Here are our shifts for" if is_first_req else "We still need to fill the following shifts for"} {day_of_event(first(events_list))}'

    #events = f'{preface} {day_of_event(first(events_list))}:\n\n' + '\n\n'.join(filter(lambda x: x, map(lambda e: event_to_str(e, schedule), events_list)))
    events = '\n\n'.join(filter(lambda x: x, map(lambda e: event_to_str(e, schedule), events_list)))

    return f'{preface}\n{events}' if events else (message or 'All shifts filled! Great job guys!')

def day_of_event(event, column_idxs=EVENT_COLUMN_IDXS):
    day_regex  = re.compile(r'^(?P<day_info>.*), \d{4}$')
    day_pieces = day_regex.match(event[column_idxs['date']]).groupdict()
    return day_pieces['day_info']

def event_to_str(event, schedule, column_idxs=EVENT_COLUMN_IDXS):
    #rem_EAs = '-'.join(map(lambda ext: str(int(ext)-num_EAs_scheduled(event[column_idxs['event_name']], schedule)), event[column_idxs['num_EAs']].split('-'))) if event[column_idxs['num_EAs']] else '?'

    #pprint(list(scheduled_shifts(event[column_idxs['event_name']], schedule)))

    #pprint(event_to_datetime_rg(event))

    #pprint(list(map(lambda shift: {(shift or event_to_datetime_rg(event)): 1}, scheduled_shifts(event[column_idxs['event_name']], schedule))))

    rem_shifts = reduce(lambda running, shift: subtract_shifts(running, {(shift if shift else event_to_datetime_rg(event)): 1}),
                        scheduled_shifts(event[column_idxs['event_name']], schedule),
                        {event_to_datetime_rg(event): event[column_idxs['num_EAs']] or '?'})
    rem_shifts_str = rem_shifts_to_str(rem_shifts)

    return f'  {event[column_idxs["event_name"]]} - {event[column_idxs["location"]]}: {rem_shifts_to_str(rem_shifts)}' if rem_shifts_str else ''

def rem_shifts_to_str(rem_shifts):
    shift_delim = '\n    '
    EA_delim    = ':' if len(rem_shifts) > 1 else ','
    return (shift_delim if len(rem_shifts) > 1 else '') + shift_delim.join(map(lambda time_rg: ' - '.join(map(time_to_clean_str, time_rg)) + f'{EA_delim} {(EAs := rem_shifts[time_rg])} EA{"" if EAs != "?" and "-" not in EAs and int(EAs) == 1 else "s"}', sorted({k: v for k, v in rem_shifts.items() if v != '0'})))

def time_to_clean_str(time):
    return time.strftime('%I:%M%p')

def event_to_datetime_rg(event, column_idxs=EVENT_COLUMN_IDXS):
    date = date_str_to_obj(event[column_idxs['date']])
    time_range = tuple(map(lambda t_s: time_str_to_obj(t_s.rstrip().lstrip()), clean_time_rg_str(event[column_idxs['report_time']] or event[column_idxs['event_time']]).split('-')))

    # if time range end if less than time range start, add one day to end date
    return (datetime.combine(date, time_rg_start(time_range)),
            datetime.combine(date + timedelta(days=(time_rg_end(time_range) < time_rg_start(time_range))), time_rg_end(time_range)))

# TODO: should this function take in a clean str or a regular str?
#   - argument for clean: establish clear pipeline instead of composing functions in other functions
def clean_time_rg_str_to_time_rg(clean_time_rg_str):
    return map(lambda t_s: time_str_to_obj(t_s.rstrip().lstrip()), clean_time_rg_str.split('-')) if clean_time_rg_str else None

def clean_time_rg_str(time_str):
    #print(f'time_rg: {time_str}')
    if not time_str:
        return time_str
    time_regex  = re.compile(r'(?P<start_hr>\d{1,2})(?::(?P<start_min>\d{2}))?\s?(?P<start_m>pm|PM|AM|am)?\s?-\s?(?P<end_hr>\d{1,2})(?::(?P<end_min>\d{2}))?\s?(?P<end_m>pm|PM|AM|am)')
    time_pieces = time_regex.match(time_str).groupdict()

    clean_time  = f'{time_pieces["start_hr"]}:{time_pieces["start_min"] or "00"}{(time_pieces["start_m"] and time_pieces["start_m"].lower()) or time_pieces["end_m"].lower()} - {time_pieces["end_hr"]}:{time_pieces["end_min"] or "00"}{time_pieces["end_m"].lower()}'

    #print(clean_time)
    return clean_time

# test with ranges on different days (11pm-1am, eg)
def subtract_shifts(minuend, subtrahend):
    ''' minuend, subtrahend are dicts with keys (start_datetime, end_datetime) and values <num_eas> '''
    # protect against the unlikely occurence that the num EAs is not filled in but people have signed up for shifts
    if minuend[first(minuend)] == '?':
        return minuend

    difference = {}

    subt_rg = first(subtrahend)
    #print(f'before reduce: {minuend}')

    # requires 2 passes through minuend
    # maybe create a single for loop 
    # or reduce that returns a tuple
    overlapping_rgs, difference = reduce(lambda running, time_rg: (running[0] + [time_rg], running[1]) if do_time_ranges_overlap(time_rg, subt_rg)
                                                                  else (running[0], add_dicts(running[1], {time_rg: minuend[time_rg]})),
                                        minuend,
                                        ([], {}))
    #print(overlapping_rgs, difference, '\n')
    #overlapping_rgs = filter(lambda time_rg: do_time_ranges_overlap(time_rg, subt_rg), minuend)
    #difference      = {time_rg: minuend[time_rg] for time_rg in minuend if not do_time_ranges_overlap(time_rg, subt_rg)}

    for minu_rg in sorted(overlapping_rgs):
        #minu_rg = tuple(map(lambda s: time_str_to_obj(s.rstrip().lstrip()), minu.split('-')))
        #subt_rg = tuple(map(lambda s: time_str_to_obj(s.rstrip().lstrip()), subtrahend.split('-')))

        og_subt_rg_end = time_rg_end(subt_rg)
        subt_rg = (time_rg_start(subt_rg), min(map(time_rg_end, (subt_rg, minu_rg))))
        
        difference[ (time_rg_start(minu_rg), time_rg_start(subt_rg)) ] = minuend[minu_rg]
        # maybe break the subtracting in the next time line into own function
        #difference[ (time_rg_start(subt_rg), time_rg_end(subt_rg))   ] = '-'.join(map(lambda ext: str(int(ext) - subtrahend[first(subtrahend)]), minuend[minu_rg].split('-')))
        difference[ (time_rg_start(subt_rg), time_rg_end(subt_rg))   ] = subtract_EAs(minuend[minu_rg], subtrahend[first(subtrahend)])
        difference[ (time_rg_end(subt_rg)  , time_rg_end(minu_rg))   ] = minuend[minu_rg]

        #pprint(difference)
        #print()

        # filter out time ranges of 0
        # this has to go through everything alerady put in difference - in the future look into constructing a local difference that's added to the larger one at the end of loop iter
        difference = {time_rg: difference[time_rg] for time_rg in difference if time_rg_end(time_rg) != time_rg_start(time_rg)}

        #pprint(difference)

        subt_rg = (time_rg_end(minu_rg), og_subt_rg_end)
        if time_rg_start(subt_rg) >= time_rg_end(subt_rg):
            return difference

def subtract_EAs(needed_str, filling):
    return '-'.join(map(lambda ext: str(int(ext) - filling), needed_str.split('-')))

def do_time_ranges_overlap(tm_rg_1, tm_rg_2):
    ''' it is assumed that tm_rg_1 is not after tm_rg_2 '''
    if tm_rg_1[0] > tm_rg_2[0]:
        return do_time_ranges_overlap(tm_rg_2, tm_rg_1)
    return tm_rg_1[1] > tm_rg_2[0]

def time_rg_start(tm_rg):
    return tm_rg[0]

def time_rg_end(tm_rg):
    return tm_rg[1]

def add_dicts(d1, d2):
    ''' returns the result of updating one dict with another. has the added benefit of not modifying the  '''
    to_return = copy(d1)
    to_return.update(d2)
    return to_return

def compose(*functions):
    return reduce(lambda f, g: lambda x: f(g(x)), functions, lambda x: x)

def time_str_to_obj(clean_time_str):
    ''' Returns time obj from a time string in the format \d{1,2}:\d{2}(am|pm) '''

    return datetime.strptime(clean_time_str, "%I:%M%p").time()

    time_regex = re.compile(r'(?P<hour>\d{1,2})(?P<minute>\d{2}(?P<xm>am|pm)')
    time_pieces = time_regex.fullmatch(clean_time_str).groupdict()

    hr = int(time_pieces['hour']) + (12 * time_pieces['xm'] == pm)
    return time(hr, int(time_pieces['minute']))

#def first(iterable):
#    return nth(iterable, 0)

def first(iterable):
    return next(iter(iterable))
        
def date_str_to_obj(date_str):
    #print(f'date_str: {date_str}')
    return datetime.strptime(date_str, "%A, %B %d, %Y").date()

    date_regex = re.compile(r'\w+, (?P<month>\w+) (?P<day>\d{1,2}), (?P<year>\d{4})')
    date_regex = re.compile(r'\w+, (?P<month>\w+) (?P<day>\d{1,2}), (?P<year>\d{4})')

    date_pieces = date_regex.search(date_str).groupdict()
    return date(int(date_pieces['year']), list(calendar.month_name).index(date_pieces['month']), int(date_pieces['day']))

def shift_str_to_time_rg_str(EA_shift_str):
    #print(f'shift: {EA_shift_str}')
    try:
        return re.search(r'\((.*)\)', EA_shift_str).group(1)
    except AttributeError:
        return ''

def num_EAs_scheduled(event_name, schedule, column_idxs=SCHED_COLUMN_IDXS):
    event_sched = first(filter(lambda e: e[column_idxs['event_name']] == event_name, schedule))
    return len(event_sched[column_idxs['EAs']].split(',')) if len(event_sched) >= column_idxs['EAs'] + 1 else 0

def scheduled_shifts(event_name, schedule, column_idxs=SCHED_COLUMN_IDXS):
    # potential for error here with recurring event: only ever grabs first. Should probably grab first after today
    sched_event = first(filter(lambda e: e[column_idxs['event_name']] == event_name, schedule))
    return map(lambda t_rg: tuple(map(lambda t_o: datetime.combine(date_str_to_obj(sched_event[column_idxs['date']]), t_o), t_rg)) if t_rg else None,
               map(compose(clean_time_rg_str_to_time_rg, clean_time_rg_str, shift_str_to_time_rg_str),
                   sched_event[column_idxs['EAs']].split(','))) if sched_event and len(sched_event) >= column_idxs['EAs'] + 1 else []

def process_args():
    to_return = {}
    to_process = iter(argv[1:])
    for arg in to_process:
        if arg == '-g':
            to_return['group'] = next(to_process)
        elif arg == '-m':
            to_return['message'] = next(to_process)
        elif arg == '-n':
            to_return['not_first'] = True
        elif arg == '-t':
            to_return['test'] = True
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
    use_test_sheet = arg_dict.get('test', False)
    is_first_req   = not arg_dict.get('not_first', False)

    sheets_API_obj = get_sheets_API_obj()
    
    next_events = list(get_next_events(get_events(sheets_API_obj, use_test_sheet), group))
    next_sched  = [ (event[EVENT_COLUMN_IDXS['event_name']],
                     event[EVENT_COLUMN_IDXS['date']],
                     event[EVENT_COLUMN_IDXS['EAs']] if len(event) > EVENT_COLUMN_IDXS['EAs'] else '')
                     for event in next_events ]
    #next_sched  = get_schedule(sheets_API_obj, use_test_sheet)
    
    #print('\n'.join(map(lambda e: f'{e}: {event_to_datetime_rg(e)}', next_events)))

    #event_time  = (datetime.combine(date.min, time(8, 0)), datetime.combine(date.min, time(11, 0)))
    #ea_shift    = (datetime.combine(date.min, time(9, 0)), datetime.combine(date.min, time(10, 0)))
    #ea_shift_2  = (datetime.combine(date.min, time(8, 30)), datetime.combine(date.min, time(10, 30)))


    #new_rg = subtract_shifts({event_time: '3'}, {ea_shift: 1})
    #pprint(f'res: {new_rg}')
    #newer_rg = subtract_shifts(new_rg, {ea_shift: 1})
    #pprint(f'res: {newer_rg}')

    #newerer_rg = subtract_shifts(newer_rg, {ea_shift_2: 1})
    #pprint(f'res: {newerer_rg}')

    #newererer_rg = subtract_shifts(newerer_rg, {event_time: 1})
    #pprint(f'res: {newererer_rg}')

    #multi_day_event = (datetime.combine(date(2020, 8, 3), time(21, 0)), datetime.combine(date(2020, 8, 4), time(2, 0)))
    #md_ea_shift = (datetime.combine(date(2020, 8, 3), time(22, 30)), datetime.combine(date(2020, 8, 4), time(0, 0)))

    #pprint(subtract_shifts({multi_day_event: '3'}, {md_ea_shift: 1}))

    if next_events:
        #print(message_from_events(next_events, get_schedule(sheets_API_obj, use_test_sheet), custom_message, is_first_req))
        print(message_from_events(next_events, next_sched, custom_message, is_first_req))
    else:
        print("No upcoming events")


if __name__ == '__main__':
    main()
