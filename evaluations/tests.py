from unittest.mock import patch

import requests
from django.test import TestCase, override_settings

from .real_environment_service import clear_environment_cache


class MockJsonResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'HTTP {self.status_code}')


@override_settings(OPENAQ_API_KEY='test-openaq-key')
class RealEnvironmentEndpointTests(TestCase):
    def setUp(self):
        clear_environment_cache()

    def tearDown(self):
        clear_environment_cache()

    @patch('evaluations.real_environment_service.requests.get')
    def test_environment_endpoint_parses_open_meteo_and_openaq(self, mock_get):
        mock_get.side_effect = [
            MockJsonResponse({
                'latitude': 41.9,
                'longitude': 12.5,
                'utc_offset_seconds': 7200,
                'current_units': {
                    'time': 'iso8601',
                    'european_aqi': 'EAQI',
                    'pm10': 'ug/m3',
                    'pm2_5': 'ug/m3',
                    'nitrogen_dioxide': 'ug/m3',
                    'ozone': 'ug/m3',
                    'grass_pollen': 'grains/m3',
                },
                'current': {
                    'time': '2026-06-20T17:00',
                    'european_aqi': 61,
                    'pm10': 14.6,
                    'pm2_5': 11.0,
                    'nitrogen_dioxide': 2.2,
                    'ozone': 135.0,
                    'grass_pollen': 22.4,
                },
            }),
            MockJsonResponse({
                'results': [{
                    'id': 7527,
                    'name': 'L.GO MAGNA GRECIA',
                    'distance': 2425.8,
                    'coordinates': {'latitude': 41.883075, 'longitude': 12.50895},
                    'sensors': [
                        {'id': 21804, 'parameter': {'name': 'pm10', 'units': 'ug/m3'}},
                        {'id': 21915, 'parameter': {'name': 'no2', 'units': 'ug/m3'}},
                    ],
                }],
            }),
            MockJsonResponse({
                'results': [
                    {
                        'sensorsId': 21804,
                        'value': 21.0,
                        'datetime': {'utc': '2026-06-20T13:00:00Z'},
                        'coordinates': {'latitude': 41.883064, 'longitude': 12.508939},
                    },
                    {
                        'sensorsId': 21915,
                        'value': 2.0,
                        'datetime': {'utc': '2026-06-20T13:00:00Z'},
                        'coordinates': {'latitude': 41.883064, 'longitude': 12.508939},
                    },
                ],
            }),
        ]

        response = self.client.get(
            '/api/environment',
            {'lat': '41.9028', 'lon': '12.4964', 'pathologies': 'respiratory,allergy'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'available')
        self.assertEqual(payload['pathologies'], ['respiratory', 'allergy'])
        self.assertIn('european_aqi', payload['pollutants'])
        self.assertIn('grass_pollen', payload['pollutants'])

        pm25 = payload['pollutants']['pm2_5']
        self.assertEqual(pm25['value'], 11.0)
        self.assertEqual(pm25['source'], 'Open-Meteo Air Quality API')
        self.assertEqual(pm25['timestamp'], '2026-06-20T17:00:00+02:00')
        self.assertEqual(pm25['lat'], 41.9)
        self.assertEqual(pm25['lon'], 12.5)

        pm10_observation = payload['pollutants']['pm10']['nearest_observation']
        self.assertEqual(pm10_observation['value'], 21.0)
        self.assertEqual(pm10_observation['source'], 'OpenAQ')
        self.assertEqual(pm10_observation['station']['id'], 7527)
        self.assertEqual(pm10_observation['timestamp'], '2026-06-20T13:00:00Z')

        locations_call = mock_get.call_args_list[1]
        self.assertEqual(locations_call.kwargs['headers']['X-API-Key'], 'test-openaq-key')

    def test_environment_endpoint_rejects_invalid_coordinates(self):
        response = self.client.get(
            '/api/environment/',
            {'lat': '100', 'lon': '12.4964', 'pathologies': 'respiratory'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'lat must be between -90 and 90'})
