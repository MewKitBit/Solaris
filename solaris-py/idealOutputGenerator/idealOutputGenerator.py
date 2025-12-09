from enum import Enum
from pandas import DataFrame
from pvlib import pvsystem, irradiance, temperature, solarposition, atmosphere, iam
from pvlib.location import Location
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

import logging
logger = logging.getLogger("idealOutputGenerator")

class TemperatureModel(Enum):
    """
    Valid temperature models for PVLib

    Notes
    -----
        The SAPM and PVSyst models produce different parameters, which is important if treated outside the
        scope of this class.
    See Also
    --------
        pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS
    """
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

class SingleDiodeMethod(Enum):
    """Valid single diode resolution methods for PVLib"""
    LAMBERTW = 'lambertw',
    NEWTON = 'newton',
    BRENTQ = 'brentq'

class IdealOutputGenerator :
    """Calculates the 'ideal' power for one module."""
    def __init__(self, location: Location, azimuth: float, tilt: float, temp_model: TemperatureModel,
                 irradiance_model: IrradianceModel, albedo: float, module: str = None,
                 module_source: ModuleSource = None, single_diode_method: SingleDiodeMethod = None):
        """
        Creates a new instance of IdealOutputGenerator with the given parameters. IdealOutputGenerator can either
        represent an ideal panel with a max wattage and set gamma_pcd or use a defined module in the CEC or Sandia
        databases.

        Parameters
        ----------
        location : Location
            The physical location of the module given by its coordinates. Uses the Location class from ``pvlib.location``

        azimuth : float
            The azimuth angle of the module.

        tilt : float
            The tilt angle of the module.

        temp_model : TemperatureModel
            The temperature model to be used for the module.

        irradiance_model : IrradianceModel
            The irradiance model to be used.

        albedo : float
            Amount of albedo at the given location.

        module : str, optional
            The name of the module to load from the databases, if any.

        module_source : ModuleSource, optional
            The database containing the module, if one is defined.

        single_diode_method : SingleDiodeMethod, optional
            The method used to solve the single diode equation (used for CEC modules) and obtain the IV curve.
        """
        self.location = location
        self.azimuth = azimuth
        self.tilt = tilt
        self.temp_params = temp_model.value
        self.temp_model = temp_model
        self.irradiance_model = irradiance_model.value
        self.albedo = albedo
        self.module = module
        self.module_source = module_source
        self.sd_method = single_diode_method

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
                logger.info(f'Loaded CEC module {module}')
                self.module = cec_modules_db[module]
            else:
                logger.error(f'No CEC module {module}, none loaded')
        else:
            logger.info(f'No module source was provided, assuming ideal module')

        # State storage
        self.output_file = None
        self.sim_parameters = None
        self.solar_pos = None
        self.total_irradiance = None
        self.cell_temperature = None
        self.ideal_power = None

    def __complete_sim_params(self):
        """
        Adds the following values to the sim_parameters dataframe if not present:
            - dni_extra: Extraterrestrial radiation (W/m^2). Solar irradiance at the top of the atmosphere.
            - airmass: Relative airmass (unitless). The optical path length through the atmosphere relative to the zenith path.
            - am_abs: Absolute airmass (unitless). Relative airmass corrected for local atmospheric pressure.
        """
        if 'dni_extra' not in self.sim_parameters.columns:
            dni_extra = irradiance.get_extra_radiation(self.sim_parameters.index)
            self.sim_parameters['dni_extra'] = dni_extra
            logger.info(f'Added dni_extra column')
        if 'airmass' not in self.sim_parameters.columns:
            airmass = atmosphere.get_relative_airmass(self.solar_pos['apparent_zenith'])
            self.sim_parameters['airmass'] = airmass
            logger.info(f'Added airmass column')
        if 'am_abs' not in self.sim_parameters.columns:
            am_abs = atmosphere.get_absolute_airmass(self.sim_parameters['airmass'], self.sim_parameters['pressure'])
            self.sim_parameters['am_abs'] = am_abs
            logger.info(f'Added am_abs column')

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

        # Calculate extra simulation parameters if not available
        self.__complete_sim_params()

        # Assign total irradiance
        self.total_irradiance = irradiance.get_total_irradiance(
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

        # Assign cell temperatures
        if self.temp_model not in [TemperatureModel.PVSYST_INSULATED, TemperatureModel.PVSYST_SEMI_INTEGRATED,
                                       TemperatureModel.PVSYST_FREESTANDING]:
            cell_temperature = temperature.sapm_cell(
                self.total_irradiance['poa_global'],
                self.sim_parameters["temp_air"],
                self.sim_parameters["wind_speed"],
                **self.temp_params,
            )

        else:
            cell_temperature = temperature.pvsyst_cell(
                poa_global=self.total_irradiance['poa_global'],
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
        Runs the core physics assuming an ideal panel.

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

    def __generate_cec_output(self):
        # Define the keys required for the physical model
        physical_params = ['n_glass', 'K_glass', 'L_glass']

        # Check if all required physical parameters exist in the module definition
        if all(key in self.module for key in physical_params):
            logger.info(f"Using Physical IAM model for {self.module.get('Name', 'Unknown Module')}")

            # Use the physical model (Fresnel + Beer-Lambert)
            iam_factor = iam.physical(
                self.sim_parameters['aoi'],
                n=self.module['n_glass'],
                K=self.module['K_glass'],
                L=self.module['L_glass']
            )

            iam_diffuse_factor = iam.physical(
                aoi=59,
                n=self.module['n_glass'],
                K=self.module['K_glass'],
                L=self.module['L_glass']
            )
        else:
            logger.debug("Physical optical parameters missing. Falling back to ASHRAE IAM model.")

            # Fallback to standard empirical model (b=0.05 is standard for flat glass)
            iam_factor = iam.ashrae(self.sim_parameters['aoi'], b=0.05)
            iam_diffuse_factor = iam.ashrae(59, b=0.05)

        effective_irradiance = (
                self.total_irradiance['poa_direct'] * iam_factor +
                self.total_irradiance['poa_diffuse'] * iam_diffuse_factor
        )

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
            method=self.sd_method,
        )

        return full_results

    def __generate_sapm_output(self):
        effective_irradiance = pvsystem.sapm_effective_irradiance(
            self.total_irradiance['poa_direct'],
            self.total_irradiance['poa_diffuse'],
            self.sim_parameters['am_abs'],
            self.sim_parameters['aoi'],
            self.module,
        )
        return pvsystem.sapm(effective_irradiance, self.cell_temperature, self.module)

    def generate_module_output(self, weather: DataFrame, output_file: str):
        """
        Runs the core physics using the loaded module.

        Args:
            weather (Series): Weather data series.
            output_file (str): Name/path of file where output will be written.
        """
        self.__operate_common_data(weather, output_file)

        if self.module_source is ModuleSource.CEC:
            full_results = self.__generate_cec_output()

        elif self.module_source is ModuleSource.SANDIA:
            full_results = self.__generate_sapm_output()

        else:
            logger.error(f"Unknown module source: {self.module_source}")
            return

        # Save to file
        full_results.to_csv(
            output_file,
            header=True,
        )