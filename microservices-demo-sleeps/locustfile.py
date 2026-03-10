#!/usr/bin/python
#
# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import random
from faker import Faker
from locust import FastHttpUser, TaskSet, between, events

fake = Faker()

products = [
    '0PUK6V6EV0',
    '1YMWWN1N4O',
    '2ZYFJ3GM2N',
    '66VCHSJNUP',
    '6E92ZMYYFZ',
    '9SIQT8TOJO',
    'L9ECAV7KIM',
    'LS4PSXUNUM',
    'OLJCESPC7Z',
]


def index(l):
  l.client.get('/')


def setCurrency(l):
  currencies = ['EUR', 'USD', 'JPY', 'CAD', 'GBP', 'TRY']
  l.client.post('/setCurrency', {'currency_code': random.choice(currencies)})


def browseProduct(l):
  l.client.get('/product/' + random.choice(products))


def viewCart(l):
  l.client.get('/cart')


def addToCart(l):
  product = random.choice(products)
  l.client.get('/product/' + product)
  l.client.post(
      '/cart', {'product_id': product, 'quantity': random.randint(1, 10)}
  )


def empty_cart(l):
  l.client.post('/cart/empty')


def checkout(l):
  addToCart(l)
  current_year = datetime.datetime.now().year + 1
  l.client.post(
      '/cart/checkout',
      {
          'email': fake.email(),
          'street_address': fake.street_address(),
          'zip_code': fake.zipcode(),
          'city': fake.city(),
          'state': fake.state_abbr(),
          'country': fake.country(),
          'credit_card_number': fake.credit_card_number(card_type='visa'),
          'credit_card_expiration_month': random.randint(1, 12),
          'credit_card_expiration_year': random.randint(
              current_year, current_year + 70
          ),
          'credit_card_cvv': f'{random.randint(100, 999)}',
      },
  )


def logout(l):
  l.client.get('/logout')


class UserBehavior(TaskSet):

  def on_start(self):
    index(self)

  tasks = {
      index: 1,
      setCurrency: 2,
      browseProduct: 10,
      addToCart: 2,
      viewCart: 3,
      checkout: 1,
  }


class WebsiteUser(FastHttpUser):
  tasks = [UserBehavior]
  wait_time = between(1, 10)


def print_stats_on_quit(environment, **kwargs):
  """Prints a summary of the test statistics when the test is finished.

  This function is a listener for Locust's 'quitting' event.
  """
  print('\n' + '=' * 80)
  print('Test Statistics Summary')
  print('=' * 80)

  # Get the total stats from the runner
  stats = environment.runner.stats.total

  #   # Calculate average requests per second using the runner's total_run_time
  #   if environment.runner.total_run_time > 0:
  #     avg_rps = stats.num_requests / environment.runner.total_run_time
  #   else:
  #     avg_rps = 0

  # Print high-level summary
  print(f'Total requests: {stats.num_requests}')
  print(f'Total failures: {stats.num_failures}')
  #   print(f'Average requests/sec: {avg_rps:.2f}')
  print(f'Average response time: {stats.avg_response_time:.2f} ms')

  # Print detailed latency distribution
  print('\nDetailed Latency Distribution (in milliseconds):')
  print('-' * 50)

  # Define a list of percentiles to report
  percentiles = [
      0.0,
      0.1,
      0.2,
      0.3,
      0.4,
      0.5,
      0.55,
      0.6,
      0.65,
      0.7,
      0.75,
      0.775,
      0.8,
      0.825,
      0.85,
      0.875,
      0.8875,
      0.9,
      0.9125,
      0.925,
      0.9375,
      0.94375,
      0.95,
      0.95625,
      0.9625,
      0.96875,
      0.975,
      0.98,
      0.985,
      0.99,
      0.995,
      0.999,
      0.9999,
      1.0,
  ]

  for p in percentiles:
    # Use a consistent width for formatting the output
    print(
        f'p{p*100:.3f}%:'.ljust(15)
        + f'{stats.get_response_time_percentile(p):.2f} ms'
    )

  print('=' * 80)


# Add the listener to the quitting event
events.quitting.add_listener(print_stats_on_quit)
