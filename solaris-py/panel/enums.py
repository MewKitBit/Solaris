from enum import Enum

class SurfaceType(Enum):
    """Valid surface types for PVLib"""
    URBAN = 'urban'
    GRASS = 'grass'
    FRESH_GRASS = 'fresh grass'
    SOIL = 'soil'
    SAND = 'sand'
    SNOW = 'snow'
    FRESH_SNOW = 'fresh snow'
    ASPHALT = 'asphalt'
    CONCRETE = 'concrete'
    ALUMINUM = 'aluminum'
    COPPER = 'copper'
    FRESH_STEEL = 'fresh steel'
    DIRTY_STEEL = 'dirty steel'
    SEA = 'sea'

class ModuleType(Enum):
    """Valid module types for PVLib"""
    GLASS_POLYMER = 'glass_polymer'
    GLASS = 'glass_glass'

class RackingModel(Enum):
    """Valid Racking models for PVLib"""
    OPEN_RACK = 'open_rack'
    CLOSE_MOUNT = 'close_mount'
    INSULATED_BACK = 'insulated_back'
    FREESTANDING = 'freestanding'
    INSULATED = 'insulated'

class TemperatureModel(Enum):
    """Valid temperature models for PVLib"""
    OPEN_RACK_GLASS = 'open_rack_glass_glass'
    CLOSE_MOUNT_GLASS = 'close_mount_glass_glass'
    OPEN_RACK_POLYMER = 'open_rack_glass_polymer'
    INSULATED_BACK_POLYMER = 'insulated_back_glass_polymer'