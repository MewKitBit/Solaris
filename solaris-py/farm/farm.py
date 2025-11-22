from pandas import Series
from pvlib import pvsystem, iotools
from pvlib.location import Location
from pvlib.pvsystem import FixedMount
from Solaris.panel import Panel, enums
import logging
import random
import string
logger = logging.getLogger("Farm")

# TODO: Add unit tests
class Farm:
    registered_ids = set()
    cec_modules_db = pvsystem.retrieve_sam('CECMod')

    def __init__(self, num_panels: int, output_average: float, output_max: float,
                 output_min: float, replacement_days: float, panel_config: dict):
        """
        Initializes a Farm instance, creating a grid of panels.

        Args:
            num_panels (int): The number of panels
        """
        self.num_panels = num_panels
        self.panel_config = panel_config
        self.output_average = output_average
        self.output_max = output_max
        self.output_min = output_min
        self.replacement_days = replacement_days
        self.panels: dict[str, Panel] = {}
        self.marked_for_switch = []

        # Environmental variables
        ## Define how dusty the farm is in general, and how much variance between days there is
        self.dirt_mu = 0.001
        self.dirt_sigma = 0.0015

        # Populate the farm with panels
        for y in range(self.num_panels):
            new_panel = self._generate_panel(self.panel_config)
            self.panels[new_panel.panel_id] = new_panel

    def _generate_panel(self, panel_config: dict):
        panel_config["panel_id"] = self._generate_id()
        return Panel(**panel_config)

    def _generate_id(self) -> str:
        """Generates a unique id for this panel in the format AA000000 and adds it to the list of registered ids."""
        gen_id = ''.join(random.choices(string.ascii_uppercase, k=2) + random.choices(string.digits, k=6))
        while gen_id in self.registered_ids:
            gen_id = ''.join(random.choices(string.ascii_uppercase, k=2) + random.choices(string.digits, k=6))
        Farm.registered_ids.add(gen_id)
        return gen_id

    def start_replacement(self, panel: Panel):
        """Marks a faulty panel in the farm for replacement."""
        if panel.days_to_replace == -1:
            chance = random.random()
            if chance < 0.04:
                panel.days_to_replace = max(self.replacement_days - 1, 0)
            elif (chance > 0.65) and (chance < 0.85):
                panel.days_to_replace = self.replacement_days + 1
            elif chance >= 0.85:
                panel.days_to_replace = self.replacement_days + 2
        logger.debug(f"Replacement days for {panel.panel_id}: {panel.days_to_replace}")

    def replace_if_needed(self):
        # TODO: Maybe separate this into two methods to avoid passing the panel_config each time
        """Checks if any panel should be replaced."""
        for panel in self.panels.values():
            if panel.days_to_replace == 0:
                # Remove the previous panel
                self.panels.pop(panel.panel_id)
                # Replace with a new one
                new_panel = self._generate_panel(self.panel_config)
                self.panels[new_panel.panel_id] = new_panel
                logger.debug(f"Replaced panel with id {panel.panel_id} for new panel {new_panel.panel_id}")

            elif panel.days_to_replace > 0:
                panel.days_to_replace -= 1
                logger.debug(f"Days left to replace panel {panel.panel_id} {panel.days_to_replace}")

    def calculate_dirt_acc(self, hours: int = 1):
        """Calculates the change in cleanliness of the overall farm over a given number of days."""
        for _ in range(hours):
            dirt_acc = random.gauss(self.dirt_mu, self.dirt_sigma)
            dirt_acc = max(0.0, dirt_acc)
            logger.debug(f"Dirt accumulation: {dirt_acc * 100}%")
            for panel in self.panels.values():
                panel.calculate_dirt_acc(dirt_acc)