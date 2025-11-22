from typing import Optional
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.pvsystem import Array, PVSystem, AbstractMount
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS
from Solaris.panel import enums

# Abandoned class for now... Might come back if I ever want to simulate an entire system
class SimEngineModelChain :
    """
    PVLib wrapper class containing all configuration for PVLib's model chain engine.

    Typical usage would follow:
    init -> set needed params -> build_model_chain
    """
    def __init__(self, location: Location, racking_model: Optional[enums.RackingModel], module_name: str,
                 surface_type: Optional[enums.SurfaceType], module_type: Optional[enums.ModuleType],
                 mount: Optional[AbstractMount], inverter_name: str, temp_model: Optional[enums.TemperatureModel]):
        """
        Initializes a simulated module instance.

        Args:
            location (Location): The geophysical location of the module.
            racking_model (RackingModel): The racking model of the module.
            module_name (str): The name of the module.
            surface_type (enums.SurfaceType): The surface type on which the module is located.
            module_type (enums.ModuleType): The module type of the module.
            mount (AbstractMount): The mount of the module.
            inverter_name (str): The name of the inverter.
            temp_model (enums.TemperatureModel): The temperature model of the module.
        """
        self.location = location
        self.racking_model = racking_model
        self.module_name = module_name
        self.surface_type = surface_type
        self.module_type = module_type
        self.mount = mount
        self.inverter_name = inverter_name
        self.temp_model = temp_model

        self.array = None
        self.losses_params = None
        self.model_chain = None
        self.module_params = None
        self.system = None

    def set_losses_params(self, soiling: int = 0, shading: int = 0, snow: int = 0, mismatch: int = 0, wiring: int = 0,
                          connections: int = 0, lid: int = 0, nameplate_rating: int = 0, age: int = 0,
                          availability: int = 0) -> None:
        """
        Sets supplied losses parameters for PVLib engine operations

        Args:
            soiling (int): Soiling level
            shading (int): Shading level
            snow (int): Snow level
            mismatch (int): Mismatch level
            wiring (int): Wiring level
            connections (int): Connection level
            lid (int): Line ID level
            nameplate_rating (int): Nameplate rating level
            age (int): Age level
            availability (int): Availability level
        """

        self.losses_params = {'soiling': soiling,
                               'shading': shading,
                               'snow': snow,
                               'mismatch': mismatch,
                               'wiring': wiring,
                               'connections': connections,
                               'lid': lid,
                               'nameplate_rating': nameplate_rating,
                               'age': age,
                               'availability': availability}

    def build_model_chain(self):
        self.array = Array(mount=self.mount,
                           surface_type=self.surface_type,
                           module=self.module_name,
                           module_type=self.module_type,
                           temperature_model_parameters=TEMPERATURE_MODEL_PARAMETERS['sapm'][self.temp_model])

        self.system = PVSystem(arrays=self.array,
                               inverter=self.inverter_name,
                               racking_model=self.racking_model,
                               losses_parameters=self.losses_params)

        self.model_chain = ModelChain(system=self.system, location=self.location)
