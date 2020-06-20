"""
Common utilities
"""

import numbers
from collections.abc import Hashable, Mapping, Callable

import numpy as np

from dreye.constants import ureg, DEFAULT_FLOAT_DTYPE, DEFAULT_INT_DTYPE


def has_units(value):
    """
    check if has units via duck-typing
    """
    return (
        hasattr(value, 'units')
        and hasattr(value, 'to')
        and hasattr(value, 'magnitude')
    )


def optional_to(obj, units, *args, **kwargs):
    """
    convert to units and return magnitude (number or array)
    """
    if has_units(obj):
        if units is None:
            obj = obj.magnitude
        else:
            obj = obj.to(units, *args, **kwargs).magnitude
    if is_numeric(obj):
        return obj
    elif is_listlike(obj):
        return np.asarray(obj)
    else:
        raise TypeError(
            f"Object of type '{type(obj)}' is not unit convertible"
        )


def get_units(obj):
    """
    get units from obj or return dimensionless units if None
    """
    if has_units(obj):
        return obj.units
    elif isinstance(obj, ureg.Unit):
        return obj
    elif is_string(obj):
        return ureg(obj).units
    else:
        return ureg(None).units


def get_value(obj):
    if has_units(obj):
        return obj.magnitude
    elif isinstance(obj, ureg.Unit):
        return DEFAULT_FLOAT_DTYPE(1.0)
    else:
        return obj


def is_hashable(obj):
    """
    returns True if allowed hashable (e.g. string, integer, tuple).
    """
    return (
        is_integer(obj)
        or is_string(obj)
        or isinstance(obj, tuple)
        or obj is None
    )
    # return isinstance(obj, (numbers.Integral, str, tuple))
    # return isinstance(obj, Hashable)  # problem with pint.Quantity


def is_string(obj):
    return isinstance(obj, str)


def is_integer(obj):
    """
    True if integer (ignoring units)
    """
    value = get_value(obj)
    if hasattr(value, 'item') and hasattr(value, 'ndim'):
        if value.ndim:
            return False
        value = value.item()
    return isinstance(value, numbers.Integral)


def is_numeric(obj):
    """
    Returns True if allowed numeric type (ignoring units)
    """
    value = get_value(obj)
    if hasattr(value, 'item') and hasattr(value, 'ndim'):
        if value.ndim:
            return False
        value = value.item()
    return isinstance(value, numbers.Number)


def is_listlike(obj):
    """
    Returns True if list-like (ignoring units)

    Allows hashable lists and non-hashable tuples, but also allows
    any object that has an ndim attribute.
    """
    value = get_value(obj)
    # assumes if has attribute ndim that it can be reformatted to an array
    if hasattr(value, 'ndim'):
        return bool(value.ndim)
    return isinstance(value, (list, tuple))


def is_dictlike(obj):
    """
    return True if object is dict-like mapping object
    """
    return isinstance(obj, Mapping)


def is_callable(obj):
    """
    Check if object if callable
    """
    return isinstance(obj, Callable)


def irr2flux(irradiance, wavelengths, return_units=None):
    """
    Convert from irradiance to photonflux.

    Parameters
    ----------
    irradiance : float or array-like
        Array in spectral irradiance units (W/m^2/nm) or units that
        can be converted to spectra irradiance.
    wavelengths : float or array-like
        Array that can be broadcast to irradiance array in nanometer units
        or units that can be converted to nanometer.
    return_units : bool, optional
        Whether to return a `pint.Quantity` or `numpy.ndarray` object.
        If None, the function will return a `pint.Quantity` if `irradiance`
        have units.

    Returns
    -------
    photonflux : numpy.ndarray or pint.Quantity
        Values converted to photonflux (mol/m^2/s/nm).
    """
    if return_units is None:
        if has_units(irradiance):
            return_units = True
        else:
            return_units = False
    # convert units
    irradiance = (
        optional_to(irradiance, 'spectralirradiance')
        * ureg('spectralirradiance')
    )
    wavelengths = optional_to(wavelengths, 'nm') * ureg('nm')
    photonflux = irradiance * wavelengths / (
        ureg.planck_constant
        * ureg.speed_of_light
        * ureg.N_A
    )
    if return_units:
        return photonflux
    else:
        return get_value(photonflux)


def flux2irr(photonflux, wavelengths, return_units=None):
    """
    Convert from photonflux to irradiance.

    Parameters
    ----------
    photonflux : float or array-like
        Array in spectral photonflux (mol/m^2/s/nm) or units that
        can be converted to photonflux.
    wavelengths : float or array-like
        Array that can be broadcast to irradiance array in nanometer units
        or units that can be converted to nanometer.
    return_units : bool, optional
        Whether to return a `pint.Quantity` or `numpy.ndarray` object.
        If None, the function will return a `pint.Quantity` if `photonflux`
        have units.

    Returns
    -------
    irradiance : numpy.ndarray or pint.Quantity
        Values converted to photonflux (W/m^2/nm).
    """
    if return_units is None:
        if has_units(photonflux):
            return_units = True
        else:
            return_units = False
    # convert units
    photonflux = (
        optional_to(photonflux, 'spectralphotonflux')
        * ureg('spectralirradiance')
    )
    wavelengths = optional_to(wavelengths, 'nm') * ureg('nm')
    irradiance = (
        photonflux * (
            ureg.planck_constant
            * ureg.speed_of_light
            * ureg.N_A)
    ) / wavelengths
    if return_units:
        return irradiance
    else:
        return get_value(irradiance)
