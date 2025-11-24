from enum import Enum
from pandas import DataFrame
from pvlib import pvsystem, irradiance, temperature
from pvlib.location import Location
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

import logging
logger = logging.getLogger("idealOutputGenerator")

class TemperatureModel(Enum):
    """Valid temperature models for PVLib"""
    SAPM_OPEN_RACK_GLASS = TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']
    SAPM_CLOSE_MOUNT_GLASS = TEMPERATURE_MODEL_PARAMETERS['sapm']['close_mount_glass_glass']
    SAPM_OPEN_RACK_POLYMER = TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_polymer']
    SAPM_INSULATED_BACK_POLYMER = TEMPERATURE_MODEL_PARAMETERS['sapm']['insulated_back_glass_polymer']
    PVSYST_FREESTANDING = TEMPERATURE_MODEL_PARAMETERS['pvsyst']['freestanding']
    PVSYST_INSULATED = TEMPERATURE_MODEL_PARAMETERS['pvsyst']['insulated']
    PVSYST_SEMI_INTEGRATED = TEMPERATURE_MODEL_PARAMETERS['pvsyst']['semi_integrated']

class IdealOutputGenerator :
    """Calculates the 'ideal' power for one module."""
    sandia_modules_db = pvsystem.retrieve_sam('SandiaMod')

    def __init__(self, location: Location, mount: pvsystem.FixedMount, module_name: str, temp_model: TemperatureModel):
        self.location = location
        self.mount = mount
        self.module_params = IdealOutputGenerator.sandia_modules_db[module_name]
        self.temp_params = temp_model
        # TODO: Could include albedo in the future for more granular control. For now left at default PVLib 0.25
        self.albedo = 0.25
        self.irradiance = None
        self.temperature = None
        self.ideal_power = None

    def calculate_irradiance(self, weather, solpos):
        self.irradiance = irradiance.get_total_irradiance(
            surface_tilt=self.mount.surface_tilt,
            surface_azimuth=self.mount.surface_azimuth,
            solar_zenith=solpos['apparent_zenith'],
            solar_azimuth=solpos['azimuth'],
            dni=weather['dni'],
            ghi=weather['ghi'],
            dhi=weather['dhi'],
            albedo=self.albedo
        )

    def calculate_temperature(self, weather):
        self.temperature = temperature.sapm_cell(
            poa_global=self.irradiance['poa_global'],
            temp_air=weather['temp_air'],
            wind_speed=weather['wind_speed'],
            **self.temp_params  # Unpack the temp model dict
        )

    def calculate_power(self):
        self.ideal_power = pvsystem.pvwatts_dc(
            effective_irradiance=self.irradiance['poa_global'],
            temp_cell=self.temperature,
            pdc0=self.module_params['pdc0'],
            gamma_pdc=self.module_params['gamma_pdc']
        )

    def generate_output(self, weather: DataFrame, solpos: DataFrame, output_file: str):
        """
        Runs the core physics using the provided weather and solpos dataframes.

        Args:
            weather (Series): Weather data series.
            solpos (Series): Solar position data series.
            output_file (str): Name/path of file where output will be written.
        """
        if weather.len() != solpos.len():
            raise ValueError("Weather length does not match solar position data length.")

        if not output_file.endswith(".csv"):
            output_file += ".csv"

        # Get irradiance on the panel
        self.calculate_irradiance(weather, solpos)
        # Get cell temperature
        self.calculate_temperature(weather)
        # Calculate ideal DC power
        self.calculate_power()

        # Save to file
        self.ideal_power.to_csv(
            output_file,
            header=True,
        )
