"""
Setup for different kinds of Tuya numbers
"""

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.components.number.const import (
    DEFAULT_MAX_VALUE,
    DEFAULT_MIN_VALUE,
    NumberDeviceClass,
)
from homeassistant.helpers.restore_state import RestoreEntity

from .device import TuyaLocalDevice
from .entity import TuyaLocalEntity, unit_from_ascii
from .helpers.config import async_tuya_setup_platform
from .helpers.device_config import TuyaEntityConfig

_LOGGER = logging.getLogger(__name__)

MODE_AUTO = "auto"
DEFAULT_HEAT_DURATION_SOURCE = "default_heat_duration"
LOCAL_NUMBER_SOURCES = {DEFAULT_HEAT_DURATION_SOURCE}


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = {**config_entry.data, **config_entry.options}
    await async_tuya_setup_platform(
        hass,
        async_add_entities,
        config,
        "number",
        TuyaLocalNumber,
    )


class TuyaLocalNumber(TuyaLocalEntity, NumberEntity, RestoreEntity):
    """Representation of a Tuya Number"""

    def __init__(self, device: TuyaLocalDevice, config: TuyaEntityConfig):
        """
        Initialise the sensor.
        Args:
            device (TuyaLocalDevice): the device API instance
            config (TuyaEntityConfig): the configuration for this entity
        """
        super().__init__()
        dps_map = self._init_begin(device, config)
        self._source = config.source
        self._attr_native_value = config.default_value
        self._value_dps = dps_map.pop("value", None)
        if self._source not in LOCAL_NUMBER_SOURCES and self._value_dps is None:
            raise AttributeError(f"{config.config_id} is missing a value dps")
        self._unit_dps = dps_map.pop("unit", None)
        self._min_dps = dps_map.pop("minimum", None)
        self._max_dps = dps_map.pop("maximum", None)
        self._decimal_dps = dps_map.pop("decimal", None)
        self._init_end(dps_map)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self._source in LOCAL_NUMBER_SOURCES:
            state = await self.async_get_last_state()
            if state is not None:
                try:
                    self._attr_native_value = float(state.state)
                except ValueError:
                    pass
            self._device.set_local_value(self._source, self._attr_native_value)

    @property
    def device_class(self):
        """Return the class of this device"""
        dclass = self._config.device_class
        if dclass:
            try:
                return NumberDeviceClass(dclass)
            except ValueError:
                _LOGGER.warning(
                    "%s/%s: Unrecognized number device class of %s ignored",
                    self._config._device.config,
                    self.name or "number",
                    dclass,
                )

    @property
    def native_min_value(self):
        if self._source in LOCAL_NUMBER_SOURCES:
            r = self._config.range
            return DEFAULT_MIN_VALUE if r is None else r["min"]
        if self._min_dps is not None:
            minimum = self._min_dps.get_value(self._device)
            if minimum is not None:
                return minimum
        r = self._value_dps.range(self._device)
        return DEFAULT_MIN_VALUE if r is None else r[0]

    @property
    def native_max_value(self):
        if self._source in LOCAL_NUMBER_SOURCES:
            r = self._config.range
            return DEFAULT_MAX_VALUE if r is None else r["max"]
        if self._max_dps is not None:
            maximum = self._max_dps.get_value(self._device)
            if maximum is not None:
                return maximum
        r = self._value_dps.range(self._device)
        return DEFAULT_MAX_VALUE if r is None else r[1]

    @property
    def native_step(self):
        if self._source in LOCAL_NUMBER_SOURCES:
            return self._config.step or 1
        return self._value_dps.step(self._device)

    @property
    def mode(self):
        """Return the mode."""
        m = self._config.mode
        if m is None:
            m = MODE_AUTO
        return m

    @property
    def native_unit_of_measurement(self):
        """Return the unit associated with this number."""
        if self._source in LOCAL_NUMBER_SOURCES:
            return unit_from_ascii(self._config.unit)
        if self._unit_dps is None:
            unit = self._value_dps.unit
        else:
            unit = self._unit_dps.get_value(self._device)

        return unit_from_ascii(unit)

    @property
    def native_value(self):
        """Return the current value of the number."""
        if self._source in LOCAL_NUMBER_SOURCES:
            return self._attr_native_value
        val = self._value_dps.get_value(self._device)
        if self._decimal_dps is not None:
            decimal = self._decimal_dps.get_value(self._device)
            if decimal is not None:
                val = val + decimal
        return val

    async def async_set_native_value(self, value):
        """Set the number."""
        _LOGGER.info("%s setting value to %s", self._config.config_id, value)
        if self._source in LOCAL_NUMBER_SOURCES:
            self._attr_native_value = value
            self._device.set_local_value(self._source, value)
            self.async_write_ha_state()
            return

        settings = {}
        if self._decimal_dps is not None:
            whole = int(value)
            decimal = value - whole
            settings = self._decimal_dps.get_values_to_set(self._device, decimal)
            value = whole

        settings = settings | self._value_dps.get_values_to_set(
            self._device, value, settings
        )

        await self._device.async_set_properties(settings)
