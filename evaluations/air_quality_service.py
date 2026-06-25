import os
from datetime import datetime, timezone

import requests


OPEN_METEO_AIR_QUALITY_URL = 'https://air-quality-api.open-meteo.com/v1/air-quality'
OPENAQ_LOCATIONS_URL = 'https://api.openaq.org/v3/locations'
REQUEST_TIMEOUT = (5, 10)


class AirQualityService:
    def __init__(self):
        self.API_URL = OPENAQ_LOCATIONS_URL
        self.open_meteo_url = OPEN_METEO_AIR_QUALITY_URL
        self.request_timeout = REQUEST_TIMEOUT

        # Default AQI value if all real providers fail (moderate).
        self.default_aqi = 3

        # Map of pollutant levels to AQI scale (1-10, with 10 being worst).
        self.pollutant_thresholds = {
            'pm25': [0, 12, 35.4, 55.4, 150.4, 250.4, 350.4, 500.4, 600, 700],
            'pm10': [0, 54, 154, 254, 354, 424, 504, 604, 800, 1000],
            'o3': [0, 54, 70, 85, 105, 125, 150, 200, 300, 400],
            'no2': [0, 53, 100, 360, 649, 1249, 1649, 2049, 2500, 3000],
            'so2': [0, 35, 75, 185, 304, 604, 804, 1004, 1500, 2000],
            'co': [0, 4.4, 9.4, 12.4, 15.4, 30.4, 40.4, 50.4, 60, 70],
        }
        self.open_meteo_parameter_map = {
            'pm2_5': 'pm25',
            'pm10': 'pm10',
            'nitrogen_dioxide': 'no2',
            'ozone': 'o3',
        }
        self.open_meteo_hourly_parameters = (
            'pm2_5',
            'pm10',
            'nitrogen_dioxide',
            'ozone',
            'european_aqi',
        )
        self.openaq_parameter_map = {
            'pm25': 'pm25',
            'pm2.5': 'pm25',
            'pm2_5': 'pm25',
            'pm10': 'pm10',
            'o3': 'o3',
            'ozone': 'o3',
            'no2': 'no2',
            'nitrogen_dioxide': 'no2',
            'so2': 'so2',
            'sulphur_dioxide': 'so2',
            'sulfur_dioxide': 'so2',
            'co': 'co',
            'carbon_monoxide': 'co',
        }

        api_key = os.getenv('OPENAQ_API_KEY', '')
        self.default_headers = {}
        if api_key:
            self.default_headers['X-API-KEY'] = api_key

    def convert_to_aqi(self, pollutant, value):
        """
        Convert pollutant concentration to AQI scale (1-10).
        """
        if value is None or pollutant not in self.pollutant_thresholds:
            return self.default_aqi

        thresholds = self.pollutant_thresholds[pollutant]

        for i, threshold in enumerate(thresholds):
            if value <= threshold:
                return i + 1

        return 10

    def get_air_quality_data(self, lat, lon):
        """
        Get air quality data for a specific location.

        Open-Meteo is the primary provider because it requires no API key and
        provides gridded coverage. OpenAQ is queried only as a fallback.
        """
        print(f'Fetching air quality data for {lat},{lon}')

        try:
            air_quality_data = self._fetch_open_meteo_air_quality(lat, lon)
            print(f'Air quality source for {lat},{lon}: Open-Meteo Air Quality API')
            return air_quality_data
        except Exception as open_meteo_error:
            print(f'Open-Meteo air quality failed for {lat},{lon}: {open_meteo_error}')

        try:
            air_quality_data = self._fetch_openaq_air_quality(lat, lon)
            print(f'Air quality source for {lat},{lon}: OpenAQ fallback')
            return air_quality_data
        except Exception as openaq_error:
            print(f'OpenAQ air quality fallback failed for {lat},{lon}: {openaq_error}')

            return {
                'airQuality': self.default_aqi,
                'error': str(openaq_error),
                'source': 'default',
                'provider': 'default',
                'isDefault': True,
            }

    def _fetch_open_meteo_air_quality(self, lat, lon):
        response = requests.get(
            self.open_meteo_url,
            params={
                'latitude': lat,
                'longitude': lon,
                'hourly': ','.join(self.open_meteo_hourly_parameters),
                'timezone': 'UTC',
                'forecast_days': 1,
            },
            timeout=self.request_timeout,
        )

        if response.status_code != 200:
            raise Exception(f'Open-Meteo Air Quality API error: {response.status_code}')

        data = response.json()
        hourly = data.get('hourly') or {}
        hourly_units = data.get('hourly_units') or {}
        times = hourly.get('time') or []
        if not times:
            raise Exception('Open-Meteo returned no hourly timestamps')

        nearest_index = self._nearest_hour_index(times)
        timestamp = times[nearest_index]
        measurements = []
        aqi_values = []

        for open_meteo_parameter, pollutant in self.open_meteo_parameter_map.items():
            values = hourly.get(open_meteo_parameter) or []
            if nearest_index >= len(values):
                continue

            value = values[nearest_index]
            if value is None:
                continue

            aqi = self.convert_to_aqi(pollutant, value)
            aqi_values.append(aqi)
            measurements.append({
                'parameter': pollutant,
                'openMeteoParameter': open_meteo_parameter,
                'value': value,
                'unit': hourly_units.get(open_meteo_parameter),
                'aqi': aqi,
            })

        if not measurements:
            raise Exception('Open-Meteo returned no usable air quality measurements')

        european_aqi = self._open_meteo_value_at(hourly, 'european_aqi', nearest_index)

        return {
            'airQuality': max(aqi_values) if aqi_values else self.default_aqi,
            'source': 'Open-Meteo Air Quality API',
            'provider': 'Open-Meteo',
            'station': 'Open-Meteo grid cell',
            'distance': 0,
            'measurements': measurements,
            'europeanAqi': european_aqi,
            'timestamp': timestamp,
            'coordinates': {
                'latitude': data.get('latitude', lat),
                'longitude': data.get('longitude', lon),
            },
            'isDefault': False,
        }

    def _fetch_openaq_air_quality(self, lat, lon):
        # Fetch new data from OpenAQ - using nearest location within 10km.
        get_by_coordinate_url = f'{self.API_URL}?coordinates={lat},{lon}&radius=10000&limit=1'
        get_by_coordinate_response = requests.get(
            get_by_coordinate_url,
            headers=self.default_headers,
            timeout=self.request_timeout,
        )

        if get_by_coordinate_response.status_code != 200:
            raise Exception(f'OpenAQ API error: {get_by_coordinate_response.status_code}')

        get_by_coordinate_data = get_by_coordinate_response.json()

        if not get_by_coordinate_data.get('results') or len(get_by_coordinate_data['results']) == 0:
            raise Exception('No air quality stations found near this location')

        location_data = get_by_coordinate_data['results'][0]

        get_latest_air_quality_url = f"{self.API_URL}/{location_data['id']}/latest"
        get_latest_air_quality_response = requests.get(
            get_latest_air_quality_url,
            headers=self.default_headers,
            timeout=self.request_timeout,
        )

        if get_latest_air_quality_response.status_code != 200:
            raise Exception(f'OpenAQ API error: {get_latest_air_quality_response.status_code}')

        get_latest_air_quality_data = get_latest_air_quality_response.json()

        if not get_latest_air_quality_data.get('results') or len(get_latest_air_quality_data['results']) == 0:
            raise Exception('No air quality measurements found for this location')

        parameters = []
        aqi_values = []
        sensor_map = {
            sensor.get('id'): sensor
            for sensor in (location_data.get('sensors') or [])
            if sensor.get('id') is not None
        }

        for param in get_latest_air_quality_data['results']:
            selected_sensor = sensor_map.get(param.get('sensorsId'))
            if not selected_sensor:
                continue

            pollutant = self._openaq_pollutant_name(selected_sensor)
            value = param.get('value')
            unit = (selected_sensor.get('parameter') or {}).get('units')

            if pollutant in self.pollutant_thresholds and value is not None:
                aqi_values.append(self.convert_to_aqi(pollutant, value))

            parameters.append({
                'parameter': pollutant,
                'lastValue': value,
                'unit': unit,
            })

        worst_aqi = max(aqi_values) if aqi_values else self.default_aqi

        return {
            'airQuality': worst_aqi,
            'source': 'OpenAQ',
            'provider': 'OpenAQ',
            'station': location_data.get('name'),
            'distance': location_data.get('distance'),
            'measurements': [{
                'parameter': p['parameter'],
                'value': p['lastValue'],
                'unit': p['unit'],
                'aqi': self.convert_to_aqi(p['parameter'], p['lastValue']),
            } for p in parameters],
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'isDefault': False,
        }

    def _nearest_hour_index(self, timestamps):
        target = datetime.now(timezone.utc)
        best_index = 0
        best_delta = None

        for index, value in enumerate(timestamps):
            parsed = self._parse_open_meteo_timestamp(value)
            if parsed is None:
                continue

            delta = abs((parsed - target).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_index = index

        return best_index

    def _parse_open_meteo_timestamp(self, value):
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _open_meteo_value_at(self, hourly, parameter, index):
        values = hourly.get(parameter) or []
        if index >= len(values):
            return None
        return values[index]

    def _openaq_pollutant_name(self, sensor):
        parameter = sensor.get('parameter') or {}
        raw_name = sensor.get('name') or parameter.get('name') or ''
        key = str(raw_name).strip().lower()
        return self.openaq_parameter_map.get(key, key)


air_quality_service = AirQualityService()
