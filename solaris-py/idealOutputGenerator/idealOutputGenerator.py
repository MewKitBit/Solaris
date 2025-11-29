from enum import Enum
from pandas import DataFrame
from pvlib import pvsystem, irradiance, temperature, solarposition, atmosphere, iam
from pvlib.location import Location
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

# TODO: Add logging to the generator
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

class IrradianceModel(Enum):
    """Valid irradiance simulation models for PVLib"""
    ISOTROPIC = 'isotropic'
    KLUCHER = 'klucher'
    HAYDAVIES = 'haydavies'
    REINDL = 'reindl'
    KING = 'king'
    PEREZ = 'perez'
    PEREZ_DRIESSE = 'perez - driesse'

class ModuleSource(Enum):
    """Valid module sources for PVLib"""
    CEC = 'CECMod'
    SANDIA = 'SandiaMod'

class IdealOutputGenerator :
    """Calculates the 'ideal' power for one module."""
    def __init__(self, location: Location, azimuth: float, tilt: float, temp_model: TemperatureModel,
                 irradiance_model: IrradianceModel, albedo: float, module: str = None,
                 module_source: ModuleSource = None):
        self.location = location
        self.azimuth = azimuth
        self.tilt = tilt
        self.temp_params = temp_model.value
        self.temp_model = temp_model
        self.irradiance_model = irradiance_model.value
        self.albedo = albedo
        self.module = module
        self.module_source = module_source

        # Load module if defined
        if module_source is ModuleSource.SANDIA:
            sandia_modules_db = pvsystem.retrieve_sam(ModuleSource.SANDIA.value)
            if module in sandia_modules_db.keys():
                logger.info(f'Loaded Sandia module {module}')
                self.module = sandia_modules_db[module]
            else:
                logger.error(f'No Sandia module {module}, none loaded')
        elif module_source is ModuleSource.CEC:
            cec_modules_db = pvsystem.retrieve_sam(ModuleSource.CEC.value)
            if module in cec_modules_db.keys():
                logger.debug(f'Loaded CEC module {module}')
                self.module = cec_modules_db[module]
            else:
                logger.error(f'No CEC module {module}, none loaded')

        # State storage
        self.output_file = None
        self.sim_parameters = None
        self.solar_pos = None
        self.total_irradiance = None
        self.cell_temperature = None
        self.ideal_power = None

    def __complete_weather(self):
        """
        Adds the following values to the weather dataframe if not present:
            - dni_extra
            - airmass
            - am_abs
        """
        if 'dni_extra' not in self.sim_parameters.columns:
            dni_extra = irradiance.get_extra_radiation(self.sim_parameters.index)
            self.sim_parameters['dni_extra'] = dni_extra
            logger.info(f'Adding dni_extra column')
        if 'airmass' not in self.sim_parameters.columns:
            airmass = atmosphere.get_relative_airmass(self.solar_pos['apparent_zenith'])
            self.sim_parameters['airmass'] = airmass
            logger.info(f'Adding airnass column')
        if 'am_abs' not in self.sim_parameters.columns:
            am_abs = atmosphere.get_absolute_airmass(self.sim_parameters['airmass'], self.sim_parameters['pressure'])
            self.sim_parameters['am_abs'] = am_abs
            logger.info(f'Adding am_abs column')

    def __operate_common_data(self, weather: DataFrame, output_file: str):
        if not output_file.endswith(".csv"):
            output_file += ".csv"

        # Overwrite with fresh weather data
        self.sim_parameters = weather.copy()

        # Pressure is needed for the solar position, so operate it before.
        if 'pressure' not in self.sim_parameters.columns:
            pressure = atmosphere.alt2pres(self.location.altitude)
            self.sim_parameters['pressure'] = pressure

        # Calculate solar position
        self.solar_pos = solarposition.get_solarposition(
            time=self.sim_parameters.index,
            latitude=self.location.latitude,
            longitude=self.location.longitude,
            altitude=self.location.altitude,
            temperature=self.sim_parameters["temp_air"],
            pressure=self.sim_parameters["pressure"],
        )

        # Calculate extra weather parameters if not available
        self.__complete_weather()

        # Assign total irradiance
        total_irradiance = irradiance.get_total_irradiance(
            self.tilt,
            self.azimuth,
            self.solar_pos['apparent_zenith'],
            self.solar_pos['azimuth'],
            self.sim_parameters['dni'],
            self.sim_parameters['ghi'],
            self.sim_parameters['dhi'],
            dni_extra=self.sim_parameters['dni_extra'],
            airmass=self.sim_parameters['airmass'],
            albedo=self.albedo,
            model=self.irradiance_model,
        )

        self.total_irradiance = total_irradiance

        # Assign cell temperatures
        if self.temp_model not in [TemperatureModel.PVSYST_INSULATED, TemperatureModel.PVSYST_SEMI_INTEGRATED,
                                       TemperatureModel.PVSYST_FREESTANDING]:
            cell_temperature = temperature.sapm_cell(
                total_irradiance['poa_global'],
                self.sim_parameters["temp_air"],
                self.sim_parameters["wind_speed"],
                **self.temp_params,
            )

        else:
            cell_temperature = temperature.pvsyst_cell(
                poa_global=total_irradiance['poa_global'],
                temp_air=self.sim_parameters["temp_air"],
                wind_speed=self.sim_parameters["wind_speed"],
                u_c=self.temp_params['u_c'],
                u_v=self.temp_params['u_v'],
            )

        self.cell_temperature = cell_temperature

        aoi = irradiance.aoi(self.tilt, self.azimuth,
                             self.solar_pos['apparent_zenith'],
                             self.solar_pos['azimuth'])
        self.sim_parameters['aoi'] = aoi

    def generate_ideal_output(self, weather: DataFrame, output_file: str, max_wattage: float, gamma_pdc: float):
        """
        Runs the core physics using the provided weather and solpos dataframes.

        Args:
            weather (Series): Weather data series.
            output_file (str): Name/path of file where output will be written.
            max_wattage (float): Maximum wattage of ideal panel.
            gamma_pdc (float): Percentage loss per Cº (i.e. -0.04 for 4%)
        """
        self.__operate_common_data(weather, output_file)

        self.ideal_power = pvsystem.pvwatts_dc(
            self.total_irradiance['poa_global'],
            self.cell_temperature,
            module_pdc0=max_wattage,
            gamma_pdc=gamma_pdc
        )

        # Save to file
        self.ideal_power.to_csv(
            output_file,
            header=True,
        )

    def generate_module_output(self, weather: DataFrame, output_file: str):
        """
        Runs the core physics using the provided weather and solpos dataframes.

        Args:
            weather (Series): Weather data series.
            output_file (str): Name/path of file where output will be written.
        """
        self.__operate_common_data(weather, output_file)

        if self.module_source is ModuleSource.CEC:
            # 1. Reflection (IAM)
            # Using ASHRAE model (standard for generic glass)
            iam_val = iam.ashrae(self.sim_parameters['aoi'], b=0.05)

            # 2. Spectrum
            # Assuming ideal spectrum (1.0) since we likely lack precipitable_water data
            spectral_loss = 1.0

            # 3. Construct Effective Irradiance
            effective_irradiance = ((self.total_irradiance['poa_direct'] * iam_val +
                                     self.total_irradiance['poa_diffuse']) * spectral_loss)

            il, i0, rs, rsh, nNsVth = pvsystem.calcparams_cec(
                effective_irradiance=effective_irradiance,
                temp_cell=self.cell_temperature,
                alpha_sc=self.module['alpha_sc'],
                a_ref=self.module['a_ref'],
                I_L_ref=self.module['I_L_ref'],
                I_o_ref=self.module['I_o_ref'],
                R_sh_ref=self.module['R_sh_ref'],
                R_s=self.module['R_s'],
                Adjust=self.module['Adjust']
            )

            full_results = pvsystem.singlediode(
                photocurrent=il,
                saturation_current=i0,
                resistance_series=rs,
                resistance_shunt=rsh,
                nNsVth=nNsVth,
                # TODO: Accept all other methods
                method='lambertw' # Standard robust solver
            )

        else:
            effective_irradiance = pvsystem.sapm_effective_irradiance(
                self.total_irradiance['poa_direct'],
                self.total_irradiance['poa_diffuse'],
                self.sim_parameters['am_abs'],
                self.sim_parameters['aoi'],
                self.module,
            )
            full_results = pvsystem.sapm(effective_irradiance, self.cell_temperature, self.module)

        self.ideal_power = full_results['p_mp']

        # Save to file
        self.ideal_power.to_csv(
            output_file,
            header=True,
        )