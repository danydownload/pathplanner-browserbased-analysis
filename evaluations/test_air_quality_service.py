from datetime import datetime, timezone

import pytest
import requests

from evaluations.air_quality_service import (
    OPEN_METEO_AIR_QUALITY_URL,
    OPENAQ_LOCATIONS_URL,
    REQUEST_TIMEOUT,
    AirQualityService,
)


class MockResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


def _current_utc_hour():
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M')


def _open_meteo_payload():
    current_hour = _current_utc_hour()
    return {
        'latitude': 44.64,
        'longitude': 10.93,
        'hourly_units': {
            'time': 'iso8601',
            'pm2_5': 'ug/m3',
            'pm10': 'ug/m3',
            'nitrogen_dioxide': 'ug/m3',
            'ozone': 'ug/m3',
            'european_aqi': 'EAQI',
        },
        'hourly': {
            'time': [current_hour],
            'pm2_5': [9.2],
            'pm10': [18.4],
            'nitrogen_dioxide': [14.1],
            'ozone': [72.0],
            'european_aqi': [42],
        },
    }


def test_open_meteo_is_primary_and_uses_timeout(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append({'url': url, 'kwargs': kwargs})
        return MockResponse(_open_meteo_payload())

    monkeypatch.setattr(requests, 'get', fake_get)

    result = AirQualityService().get_air_quality_data(44.6471, 10.9252)

    assert result['source'] == 'Open-Meteo Air Quality API'
    assert result['provider'] == 'Open-Meteo'
    assert result['isDefault'] is False
    assert result['europeanAqi'] == 42
    assert [measurement['parameter'] for measurement in result['measurements']] == [
        'pm25',
        'pm10',
        'no2',
        'o3',
    ]
    assert len(calls) == 1
    assert calls[0]['url'] == OPEN_METEO_AIR_QUALITY_URL
    assert calls[0]['kwargs']['timeout'] == REQUEST_TIMEOUT
    assert calls[0]['kwargs']['params']['hourly'] == 'pm2_5,pm10,nitrogen_dioxide,ozone,european_aqi'


def test_openaq_is_fallback_only_and_all_calls_use_timeout(monkeypatch):
    monkeypatch.setenv('OPENAQ_API_KEY', 'test-key')
    calls = []

    def fake_get(url, **kwargs):
        calls.append({'url': url, 'kwargs': kwargs})

        if url == OPEN_METEO_AIR_QUALITY_URL:
            raise requests.Timeout('Open-Meteo timed out')

        if url.startswith(OPENAQ_LOCATIONS_URL) and url.endswith('/latest'):
            return MockResponse({
                'results': [
                    {'sensorsId': 101, 'value': 11.5},
                    {'sensorsId': 102, 'value': 34.0},
                ],
            })

        if url.startswith(OPENAQ_LOCATIONS_URL):
            return MockResponse({
                'results': [{
                    'id': 7527,
                    'name': 'Modena station',
                    'distance': 1200.0,
                    'sensors': [
                        {'id': 101, 'parameter': {'name': 'pm25', 'units': 'ug/m3'}},
                        {'id': 102, 'parameter': {'name': 'no2', 'units': 'ug/m3'}},
                    ],
                }],
            })

        pytest.fail(f'unexpected URL: {url}')

    monkeypatch.setattr(requests, 'get', fake_get)

    result = AirQualityService().get_air_quality_data(44.6471, 10.9252)

    assert result['source'] == 'OpenAQ'
    assert result['provider'] == 'OpenAQ'
    assert result['station'] == 'Modena station'
    assert result['isDefault'] is False
    assert [call['kwargs']['timeout'] for call in calls] == [REQUEST_TIMEOUT, REQUEST_TIMEOUT, REQUEST_TIMEOUT]
    assert calls[0]['url'] == OPEN_METEO_AIR_QUALITY_URL
    assert calls[1]['url'].startswith(OPENAQ_LOCATIONS_URL)
    assert calls[2]['url'] == f'{OPENAQ_LOCATIONS_URL}/7527/latest'
    assert calls[1]['kwargs']['headers']['X-API-KEY'] == 'test-key'
