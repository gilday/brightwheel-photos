#!/usr/bin/env python3

import argparse
import json
from urllib.parse import urlparse

import requests

def main():
    parser = argparse.ArgumentParser(description='Download photos from Brightwheel')
    parser.add_argument('--email', help='')
    parser.add_argument('--password', help='')
    parser.add_argument('--directory', help='')
    args = parser.parse_args()

    with requests.Session() as s:
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

        params = {'page': 0, 'page_size': 10, 'action_type': 'ac_photo', 'include_parent_actions': 'true'}
        headers = {
                'Accept': 'application/json',
                'X-CSRF-Token': csrf,
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.16; rv:83.0) Gecko/20100101 Firefox/83.0'
        }
        r = s.get('https://schools.mybrightwheel.com/api/v1/students/4a1fe4c5-0a33-45c4-9e1c-a470fb28d3e2/activities', headers=headers, params=params)
        data = r.json()
        for activity in data['activities']:
            url = activity['media']['image_url']
            path = urlparse(url).path.split('/')[-1]
            with open('{directory}/{path}'.format(directory=args.directory, path=path), 'wb') as f:
                r = s.get(url)
                f.write(r.content)




if __name__ == "__main__":
    main()
