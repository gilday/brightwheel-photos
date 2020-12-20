#!/usr/bin/env python3

import argparse
from datetime import datetime
import email
import io
import json
import os
import sys
from urllib.parse import urlparse

from PIL.PngImagePlugin import PngImageFile, PngInfo
import requests

def main():
    parser = argparse.ArgumentParser(description='Download photos from Brightwheel')
    parser.add_argument('--email', required=True, help='email used for Brightwheel account')
    parser.add_argument('--password', required=True, help='password used for Brightwheel account')
    parser.add_argument('--directory', required=True, help='directory in which to save the photos')
    parser.add_argument('--student-id', help='Brightwheel student ID')
    args = parser.parse_args()

    os.makedirs(args.directory, exist_ok=True)
    with requests.Session() as s:
        login(s, args.email, args.password)
        # try to find student_id if not provided
        student_id = args.student_id
        if not student_id:
            students = find_students(s)
            if len(students) > 1:
                print('Multiple students detected: pick one', file=sys.stderr)
                for student in students:
                    print('{} {} {}'.format(student['object_id'],student['first_name'],student['last_name'], file=sys.stderr))
                sys.exit(1)
                return
            student_id = students[0]['object_id']


        # find and save all photos for the student
        for activity in find_photo_activities(s):
            print(json.dumps(activity))
            url = activity['media']['image_url']
            r = s.get(url)
            image = PngImageFile(io.BytesIO(r.content))
            metadata = PngInfo()
            created_at = datetime.strptime(activity['created_at'], "%Y-%m-%dT%H:%M:%S.%f%z")
            metadata.add_text('Creation Time', email.utils.format_datetime(created_at))
            note = activity['note']
            if note:
                metadata.add_text('Description', activity['note'])
            path = urlparse(url).path.split('/')[-1][:-3]
            image.save('{directory}/{path}.jpg'.format(directory=args.directory, path=path), pnginfo=metadata)


def login(s, email, password):
    # login
    login_data = {
        'user': {
            'email': email,
            'password': password
        }
    }
    headers = {
        'X-Client-Name': 'web',
        'X-Client-Version': 'b15cec31e66fa803de35b53260872aa7e5e84e29',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.16; rv:83.0) Gecko/20100101 Firefox/83.0'
    }
    r = s.post('https://schools.mybrightwheel.com/api/v1/sessions', headers=headers, json=login_data)
    r.raise_for_status()
    csrf_token = r.json()['csrf']
    headers['X-CSRF-Token'] = csrf_token
    s.headers.update(headers)



def find_students(s):
    headers = {
        'Accept': 'application/json'
    }
    r = s.get('https://schools.mybrightwheel.com/api/v1/users/me', headers=headers)
    r.raise_for_status()
    guardian_id = r.json()['object_id']

    r = s.get('https://schools.mybrightwheel.com/api/v1/guardians/{}/students'.format(guardian_id))
    return [record['student'] for record in r.json()['students']]


def find_photo_activities(s):
    page = 0
    page_size = 10
    params = {'page_size': page_size, 'action_type': 'ac_photo', 'include_parent_actions': 'true'}
    while (True):
        params['page'] = page
        params['offset'] = page * page_size
        r = s.get('https://schools.mybrightwheel.com/api/v1/students/4a1fe4c5-0a33-45c4-9e1c-a470fb28d3e2/activities', params=params)
        data = r.json()
        activities = data['activities']
        if len(activities) <= 0:
            return
        for activity in activities:
            yield activity
        page += 1
 

if __name__ == "__main__":
    main()
