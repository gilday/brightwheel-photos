#!/usr/bin/env python3

import argparse
import json
import os
import sys
from urllib.parse import urlparse

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

        # login
        login_data = {
            'user': {
                'email': args.email,
                'password': args.password
            }
        }
        headers = {
                'Accept': 'application/json',
                'X-Client-Name': 'web',
                'X-Client-Version': 'b15cec31e66fa803de35b53260872aa7e5e84e29',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.16; rv:83.0) Gecko/20100101 Firefox/83.0'
        }
        r = s.post('https://schools.mybrightwheel.com/api/v1/sessions', headers=headers, json=login_data)
        r.raise_for_status()
        csrf = r.json()['csrf']

        # try to find student_id if not provided
        student_id = args.student_id
        if not student_id:
            r = s.get('https://schools.mybrightwheel.com/api/v1/users/me', headers=headers)
            guardian_id = r.json()['object_id']

            r = s.get('https://schools.mybrightwheel.com/api/v1/guardians/{}/students'.format(guardian_id))
            data = r.json()
            if data['count'] > 1:
                print('Multiple students detected: pick one', file=sys.stderr)
                for student in data['students']:
                    student = student['student']
                    print('{} {} {}'.format(student['object_id'],student['first_name'],student['last_name'], file=sys.stderr))
                sys.exit(1)
                return
            student_id = data['students'][0]['student']['object_id']


        # find and save all photos for the student
        params = {'page': 0, 'page_size': 10, 'action_type': 'ac_photo', 'include_parent_actions': 'true'}
        headers = {
                'Accept': 'application/json',
                'X-CSRF-Token': csrf,
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.16; rv:83.0) Gecko/20100101 Firefox/83.0'
        }
        page = 0
        page_size = 10
        while (True):
            params['page'] = page
            params['offset'] = page * page_size
            r = s.get('https://schools.mybrightwheel.com/api/v1/students/4a1fe4c5-0a33-45c4-9e1c-a470fb28d3e2/activities', headers=headers, params=params)
            data = r.json()
            if data['count'] <= 0:
                return
            for activity in data['activities']:
                url = activity['media']['image_url']
                path = urlparse(url).path.split('/')[-1]
                with open('{directory}/{path}'.format(directory=args.directory, path=path), 'wb') as f:
                    r = s.get(url)
                    f.write(r.content)
            page += 1


if __name__ == "__main__":
    main()
