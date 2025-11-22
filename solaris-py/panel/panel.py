from math import exp
from typing import Optional
import random
import logging
logger = logging.getLogger("Panel")

# TODO: Add unit tests for the class
class Panel:
    """Represents a single solar panel in a simulation."""
    hours_in_year = 8760

    def __init__(self,
                 panel_id: str,
                 random_seed: Optional[int],
                 max_output: float,
                 current_degradation: float,
                 fluctuation: float,
                 failure_rate: float,
                 failure_progression_rate: float,
                 annual_degradation: float,
                 first_phase_degradation: float,
                 active_hours: int = 0,
                 health: float = 1.0,
                 failing: bool = False,
                 cleanliness: float = 1.0):
        """
        Initializes a Panel instance.

        Args:
            panel_id (str): The panel's unique identifier.
            max_output (float): Maximum potential output in Watts.
            current_degradation (float): Current degradation percentage of the panel's output.
            fluctuation (float): Random fluctuation range (e.g., 0.05 for +/- 5%).
            failure_rate (float): Probability of failure per hour (0.0 to 1.0).
            failure_progression_rate (float): How much health is lost per hour once a failure has begun.
            annual_degradation (float): The annual degradation rate after settlement (e.g., 0.005 for 0.5% per year).
            first_phase_degradation (float): The initial degradation rate as a new panel (e.g., 0.02 for 2% per year).
            active_hours (int): Number of hours panel has been functioning.
            health (float): Current health index of the panel.
            failing (bool): Whether the panel is failing or not.
            cleanliness (float): Current cleanliness index of the panel.
        """
        self.panel_id = panel_id
        self.random = random if random_seed is None else random.Random(random_seed)
        self.max_output = max_output
        self.fluctuation = fluctuation
        self.failure_rate = failure_rate
        self.current_degradation = current_degradation # Accumulated degradation
        self.failure_progression_rate = failure_progression_rate
        self.first_phase_degradation = first_phase_degradation / Panel.hours_in_year  # e.g., 0.02 for 2%
        self.annual_degradation = annual_degradation / Panel.hours_in_year # e.g., 0.005 for 0.5%

        # State variables
        ## Uptime
        self.active_hours = active_hours
        ## Days until replacement (if replacing)
        self.days_to_replace = -1
        ## Health status
        self.current_output = 0.0
        self.health = health # 1.0 is perfect, 0.0 is completely failed.
        self.failing = failing
        ## Dirt accumulation
        self.cleanliness = cleanliness
        self.min_cleanliness = 0.8
        ## Algorithm detected failure
        self.failure_detected = False

        logger.debug(f"Initialized Panel with id {self.panel_id}")

    def _time_increment(self, hours: int = 1):
        """Advances the panel's internal clock by amount of days specified."""
        self.active_hours += hours
        logger.debug(f"Added {hours} days to {self.panel_id} active days. Result: {self.active_hours} hours.")

    def _update_health(self):
        """
        Checks if the panel should begin failing, and progresses the failure if it already has.
        """
        # Check if the panel should start failing (if it's not already)
        if not self.failing:
            if self.random.random() < (1 - (1 - self.failure_rate)**self.active_hours):
                self.failing = True
                logger.info(f"Panel {self.panel_id} started failing.")

        # If the panel is in the process of failing, degrade its health
        if self.failing:
            self.health -= self.failure_progression_rate * self.active_hours
            self.health = max(0.0, self.health)  # Ensure health doesn't go below 0
            logger.debug(f"Panel {self.panel_id} reduced health to {self.health}")

    def _calculate_degradation(self):
        """
        Calculates total degradation based on a biphasic model.
        - A higher rate is applied for the first year.
        - A lower, steady rate is applied for all subsequent years.
        """
        degradation_to_add = 0.0
        year_one_boundary = Panel.hours_in_year

        # Case 1: The entire time step occurs AFTER the first year.
        if self.active_hours >= year_one_boundary:
            degradation_to_add = self.active_hours * self.annual_degradation

        # Case 2: The entire time step occurs WITHIN the first year.
        elif self.active_hours + self.active_hours <= year_one_boundary:
            degradation_to_add = self.active_hours * self.first_phase_degradation

        # Case 3: The time step CROSSES the one-year boundary.
        else:
            hours_left_in_year_one = year_one_boundary - self.active_hours
            degradation_to_add += hours_left_in_year_one * self.first_phase_degradation

            hours_after_year_one = self.active_hours - hours_left_in_year_one
            degradation_to_add += hours_after_year_one * self.annual_degradation

            logger.debug(f"Panel {self.panel_id} crossed year threshold")

        self.current_degradation += degradation_to_add
        self.current_degradation = min(1.0, self.current_degradation)

    def calculate_dirt_acc(self, dirt_acc: float):
        """Calculates the change in cleanliness of the panel given an overall farm event."""
        # Definition of constants
        dirt_variance_mu = 0.0
        dirt_variance_sigma = 0.0005

        remaining_potential = self.cleanliness - self.min_cleanliness

        variance = self.random.gauss(dirt_variance_mu, dirt_variance_sigma)

        cleanliness_lost = remaining_potential * (dirt_acc + variance)
        self.cleanliness -= cleanliness_lost

        self.cleanliness = max(self.cleanliness, self.min_cleanliness)
        return self.cleanliness

    def clean(self, rain_amount: float):
        """Cleans the panel given a rain amount or manual cleaning."""
        # Manual cleaning
        if rain_amount == 0.0:
            self.cleanliness = 1.0
            logger.debug(f"Panel {self.panel_id} cleaned manually.")
            return

        # Rain event
        rain_threshold = 2.0  # (mm) Rain below this amount has little to no positive effect.
        cementation_effect = 0.005  # Slight decrease in cleanliness for very light rain.
        max_effect = 0.70  # A heavy downpour removes at most 70% of dirt.
        effective_rate = 0.15  # Controls how quickly the rain becomes effective.

        # 1. Handle the rain threshold and cementation effect.
        if rain_amount < rain_threshold:
            self.cleanliness -= cementation_effect
            self.cleanliness = max(self.min_cleanliness, self.cleanliness)
            return

        # 2. Calculate the effectiveness of the rain with diminishing returns.
        # This formula creates an S-curve where effectiveness rises quickly then flattens.
        rain_effectiveness = max_effect * (1 - exp(effective_rate * rain_amount))

        # 3. Apply the cleaning effect.
        dirt_to_remove = 1.0 - self.cleanliness
        cleanliness_gain = dirt_to_remove * rain_effectiveness

        self.cleanliness += cleanliness_gain

        # 4. Ensure cleanliness doesn't exceed 1.0.
        self.cleanliness = min(1.0, self.cleanliness)

    def calculate_output(self, ideal_output: float, hours: int = 1) -> float:
        """
        Calculates the current power output based on state and external factors.

        Returns:
            float: The current output in Watts.
        """
        self._time_increment(hours)
        self._update_health()

        if self.health <= 0.0:
            self.current_output = 0.0
            return 0.0

        self._calculate_degradation()

        # Fluctuation is amplified as health drops. Amplification is capped to prevent extreme values.
        instability_factor = min(10.0, 1.0 / (self.health + 1e-6))  # Cap at 10x normal fluctuation
        current_fluctuation = self.fluctuation * instability_factor
        fluctuation = self.random.uniform(-current_fluctuation, current_fluctuation)

        self.current_output = ideal_output * fluctuation * self.cleanliness * self.current_degradation

        return self.current_output