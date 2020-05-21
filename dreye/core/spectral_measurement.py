"""Class to define spectral measurement
"""

import warnings
import numpy as np
from scipy.optimize import lsq_linear
from scipy.interpolate import interp1d
from sklearn.isotonic import IsotonicRegression

from dreye.utilities import (
    has_units, is_numeric, asarray,
    _convert_get_val_opt
)
from dreye.constants import ureg
from dreye.core.spectrum import AbstractSpectrum, Spectrum
from dreye.core.signal import Signal, SignalContainer
from dreye.core.domain import Domain
from dreye.err import DreyeError


class CalibrationSpectrum(AbstractSpectrum):
    """Subclass of signal to define calibration spectrum.
    Units must be convertible to microjoule
    """

    def __init__(
        self,
        values,
        domain=None,
        units='microjoule',
        labels=None,
        area=None,
        area_units='cm ** 2',
        **kwargs
    ):

        if area is None and not isinstance(values, CalibrationSpectrum):
            raise DreyeError(
                f"Must provide 'area' argument to "
                f"initialize {type(self).__name__}."
            )

        super().__init__(
            values=values,
            domain=domain,
            units=units,
            labels=labels,
            **kwargs
        )

        # set area key in attribute
        if area is None:
            area = self.attrs.get('_area', area)
        if not is_numeric(area):
            raise DreyeError(f"'area' argument must be a numeric value, "
                             f"but is of type '{type(area)}'.")
        elif has_units(area):
            area = area.to(area_units)
        else:
            area = area * ureg(area_units)
        self.attrs['_area'] = area

        if self.ndim != 1:
            raise DreyeError(
                "Calibration spectrum must always be one dimensional"
            )

    @property
    def area(self):
        """
        """

        return self.attrs['_area']


class MeasuredSpectrum(Spectrum):
    """
    Subclass of Signal that also stores a spectrum associated to a
    spectrum measurement.

    Methods
    -------
    fit # fitting spectrum with a set of spectra
    conversion to photonflux

    Parameters
    ----------
    values : 2D
    """

    _label_class = Domain
    _force_labels = False

    def __init__(
        self, *args,
        zero_boundary=None,
        max_boundary=None,
        zero_is_lower=None,
        label_units=None,
        **kwargs
    ):

        # TODO label units resolution

        super().__init__(*args, **kwargs)

        if not self.ndim == 2:
            raise DreyeError('MeasuredSpectrum must be two-dimensional.')
        if not isinstance(self.labels, Domain):
            try:
                # check if label idcs are sorted
                sorted_idcs = np.argsort(self.labels, axis=0)
                # domain will automatically sort label values
                self._labels = Domain(self.labels, units=label_units)
                # need to sort signal values if not sorted
                if not np.all(np.diff(sorted_idcs) == 1):
                    warnings.warn(
                        'Domain labels are not sorted ascendingly. '
                        'Sorting signal values ascendingly. '
                        'ATTENTION: other attributes, such as signal_min '
                        'and signal_max, are not being sorted.'
                    )
                    self._values = np.take_along_axis(
                        self.magnitude,
                        sorted_idcs,
                        axis=self.other_axis
                    )
            except Exception:
                raise DreyeError(
                    'Labels must be domain or be able'
                    ' to be made into domain.'
                )
        elif label_units is not None:
            self._labels = self.labels.to(label_units)

        if self.name is None:
            raise DreyeError(f'name variable must be provided '
                             f'for {type(self).__name__} instance.')

        if zero_boundary is not None:
            self.attrs['_zero_boundary'] = zero_boundary
        if max_boundary is not None:
            self.attrs['_max_boundary'] = max_boundary
        if zero_is_lower is not None:
            self.attrs['_zero_is_lower'] = zero_is_lower

        # convert to correct units, but only return value
        self.attrs['_zero_boundary'] = _convert_get_val_opt(
            self.attrs.get('_zero_boundary', None), self.labels.units
        )
        self.attrs['_max_boundary'] = _convert_get_val_opt(
            self.attrs.get('_max_boundary', None), self.labels.units
        )

        if (
            self.attrs.get('_zero_is_lower', None) is None
            and (
                self.attrs['_max_boundary'] is None
                or self.attrs['_zero_boundary'] is None
            )
        ):
            raise DreyeError(
                'Must provide zero_is_lower or max and zero boundary.'
            )

        if self.attrs.get('_zero_is_lower', None) is None:
            self.attrs['_zero_is_lower'] = (
                self.zero_boundary < self.max_boundary
            )

    @property
    def boundary_units(self):
        return self.labels.units

    @property
    def zero_is_lower(self):
        """
        ascending or descending input values with intensity values.

        Should never be None
        """
        return self.attrs['_zero_is_lower']

    @property
    def zero_boundary(self):
        return self.attrs['_zero_boundary']

    @property
    def max_boundary(self):
        return self.attrs['_max_boundary']

    @property
    def inputs(self):
        """alias for labels
        """
        return self.labels

    def to_measured_spectra(self, units='uE'):
        return MeasuredSpectraContainer([self], units=units)


class MeasuredSpectraContainer(SignalContainer):
    """Container for measured spectra

    Assumes each measured spectrum has a the same spectral
    distribution across intensities (e.g. LEDs).
    """

    _xlabel = 'wavelength (nm)'
    _cmap = 'viridis'
    _init_keys = [
        '_zero_is_lower',
        '_zero_boundary',
        '_max_boundary',
        '_intensities_list',
        '_intensities',
        '_normalized_spectrum_list',
        '_normalized_spectrum',
        '_mapper'
    ]
    _allowed_instances = MeasuredSpectrum

    def map(self, values, units=True):
        """

        Parameters
        ----------
        values : array-like
            samples x channels in intensity units set.
        """

        values = _convert_get_val_opt(values, units=(self.units * ureg('nm')))
        values = self._pre_mapping(values)
        assert values.ndim < 3, 'values must be 1 or 2 dimensional'

        x = self._mapper_func(np.atleast_2d(values))

        if values.ndim == 1:
            x = x[0]

        return self._post_mapping(x, units=units)

    def _mapper_func(self, x):
        """
        Function that maps intensity values to input values.
        """
        # create mapper functions if they don't exist
        if self._mapper is None:
            mappers = []
            for idx, ele in enumerate(self):
                mappers.append(self._get_single_mapper(idx, ele))
            self._mapper = mappers

        y = np.zeros(x.shape)
        for idx in range(x.shape[1]):
            y[:, idx] = self._mapper[idx](x[:, idx])
        return y

    def _get_single_mapper(self, idx, ele):
        """mapping using isotonic regression
        """

        # 1D signal
        signal = self.intensities_list[idx]
        domain = signal.domain
        zero_is_lower = ele.zero_is_lower
        zero_boundary = ele.zero_boundary

        y = signal.magnitude
        x = domain.magnitude

        # add zero if it does not exist yet
        if zero_boundary is None:
            pass
        # a little redundant but should ensure safety of method
        elif zero_is_lower and zero_boundary < np.min(x):
            x = np.concatenate([[zero_boundary], x])
            y = np.concatenate([[0], y])
        # a little redundant but should ensure safety of method
        elif not zero_is_lower and zero_boundary > np.max(x):
            x = np.concatenate([x, [zero_boundary]])
            y = np.concateante([y, [0]])

        # perform isotonic regression
        isoreg = IsotonicRegression(
            # lower and upper intensity values
            y_min=self.bounds[0][idx],
            y_max=self.bounds[1][idx],
            increasing=zero_is_lower
        )

        new_y = isoreg.fit_transform(x, y)
        return interp1d(
            new_y, x,
            bounds_error=False,
            # allow going beyond bounds
            # but fill values to lower and upper bounds
            # lower and upper input values
            fill_value=tuple(self.domain_bounds[idx])
        )

    @property
    def label_units(self):
        """
        units of each input for each measured spectra.

        If label units are not the same, this will throw an error
        """
        units = [ele.labels.units for ele in self]
        if len(set(units)) > 1:
            raise DreyeError('Input units do not match.')
        return units[0]

    def _post_mapping(self, x, units=True):
        """
        Adds units after mapping and clips input values if necessary
        to lower and upper boundary.
        """

        if units:
            units = self.label_units
        else:
            units = 1

        return np.clip(
            x,
            a_min=self.lower_boundary[None, :],
            a_max=self.upper_boundary[None, :]
        ) * units

    def _pre_mapping(self, values):
        """
        processing of intensity values before mapping

        Checks that all intensity values are within bounds.
        """
        min = np.atleast_2d(self.bounds[0])
        max = np.atleast_2d(self.bounds[1])

        truth = np.all(np.atleast_2d(values) >= min)
        truth &= np.all(np.atleast_2d(values) <= max)
        assert truth, 'some values to be mapped are out of bounds.'

        return values

    @property
    def intensities_list(self):
        """
        List of intensities (integral across spectrum) for each
        measured spectrum.
        """
        if self._intensities_list is None:
            self._intensities_list = [
                Signal(
                    ele.integral,
                    domain=ele.labels,
                    labels=ele.name,
                )
                for ele in self
            ]

        return self._intensities_list

    @property
    def intensities(self):
        """
        Concatenated overall intensities (integral) values of each
        measured spectrum.
        """
        # will only work if domain and values have same units
        if self._intensities is None:
            signal = self.intensities_list[0]
            if len(self.intensities_list) == 1:
                signal = signal._expand_dims(1)
            else:
                for ele in self.intensities_list[1:]:
                    signal = signal.concat(ele)
            self._intensities = signal
        return self._intensities

    @property
    def zero_is_lower(self):
        """
        Whether zero intensity input value is lower than the max intensity
        input value.
        """
        if self._zero_is_lower is None:
            self._zero_is_lower = np.array([
                ele.zero_is_lower for ele in self
            ])
        return self._zero_is_lower

    @property
    def zero_boundary(self):
        """
        Boundary of inputs corresponding to zero intensity spectrum
        """
        if self._zero_boundary is None:
            self._zero_boundary = np.array([
                ele.zero_boundary
                if ele is not None
                else np.nan
                for ele in self
            ])

        return self._zero_boundary

    @property
    def max_boundary(self):
        """
        Boundary of inputs corresponding to maximum intensity spectrum
        """
        if self._max_boundary is None:
            self._max_boundary = np.array([
                ele.max_boundary
                if ele is not None
                else np.nan
                for ele in self
            ])

        return self._max_boundary

    @property
    def starts(self):
        """
        lowest input value tested (e.g. 0 volts)
        """
        return np.array([
            ele.labels.start for ele in self
        ])

    @property
    def ends(self):
        """
        highest input value tested (e.g. 5 volts)
        """
        return np.array([
            ele.labels.end for ele in self
        ])

    @property
    def bounds(self):
        """
        Intensity bounds for the Measured Spectra
        (maximum or minimum irradiance or photon flux).
        """

        # TODO use boundaries instead?
        bounds = np.array([
            [np.min(ele.magnitude), np.max(ele.magnitude)]
            for ele in self.intensities_list
        ])

        bounds[~np.isnan(self.zero_boundary), 0] = 0

        return tuple(bounds.T)

    @property
    def domain_bounds(self):
        """
        Bounds for the inputs, such as volts or PWM.
        """
        return np.array([self.lower_boundary, self.upper_boundary]).T

    @property
    def lower_boundary(self):
        """
        Lower boundary of inputs, e.g. 0 volts.
        """
        lower_boundary = np.zeros(self.zero_is_lower.shape)
        lower_boundary[self.zero_is_lower] = \
            self.zero_boundary[self.zero_is_lower]
        lower_boundary[~self.zero_is_lower] = \
            self.max_boundary[~self.zero_is_lower]
        lower_boundary[np.isnan(lower_boundary)] = self.starts[
            np.isnan(lower_boundary)]
        return lower_boundary

    @property
    def upper_boundary(self):
        """
        Uppoer boundary of inputs, e.g. 5 volts.
        """
        upper_boundary = np.zeros(self.zero_is_lower.shape)
        upper_boundary[~self.zero_is_lower] = \
            self.zero_boundary[~self.zero_is_lower]
        upper_boundary[self.zero_is_lower] = \
            self.max_boundary[self.zero_is_lower]
        upper_boundary[np.isnan(upper_boundary)] = self.ends[
            np.isnan(upper_boundary)]
        return upper_boundary

    @property
    def normalized_spectrum_list(self):
        if self._normalized_spectrum_list is None:
            ele_list = []
            for ele in self:
                ele = ele.mean(axis=ele.other_axis)
                ele_list.append(
                    ele.normalized_signal
                )
            self._normalized_spectrum_list = ele_list
        return self._normalized_spectrum_list

    @property
    def normalized_spectrum(self):
        if self._normalized_spectrum is None:
            signal = self.normalized_spectrum_list[0]
            if len(self.normalized_spectrum_list) == 1:
                signal = signal._expand_dims(1)
            else:
                for ele in self.normalized_spectrum_list[1:]:
                    signal = signal.concat(ele)
            self._normalized_spectrum = signal
        return self._normalized_spectrum

    @property
    def wavelengths(self):
        return self.normalized_spectrum.domain

    @property
    def uE(self):
        """
        Convert to micro photon flux
        """
        return type(self)(
            [ele.uE for ele in self]
        )

    @property
    def irradiance(self):
        """
        Convert to irradiance
        """
        return type(self)(
            [ele.irradiance for ele in self]
        )

    @property
    def photonflux(self):
        """
        Convert to photon flux
        """
        return type(self)(
            [ele.photonflux for ele in self]
        )

    def fit(self, spectrum, return_res=False, return_fit=False, units=True):
        """fit a single spectrum
        """

        # TODO move to stim_estimator

        assert isinstance(spectrum, Spectrum)
        assert spectrum.ndim == 1

        spectrum = spectrum.copy()
        spectrum.units = self.units

        spectrum, normalized_sources = spectrum.equalize_domains(
            self.normalized_spectrum, equalize_dimensions=False)

        b = asarray(spectrum)
        A = asarray(normalized_sources)

        res = lsq_linear(A, b, bounds=self.bounds)

        # Class which incorportates the following
        # values=res.x, units=self.units, axis0_labels=self.labels

        if units:
            weights = res.x * self.units * ureg('nm')
        else:
            weights = res.x

        fitted_spectrum = (
            self.normalized_spectrum * weights[None, :]
        ).sum(axis=1)

        if return_res and return_fit:
            return weights, res, fitted_spectrum
        elif return_res:
            return weights, res
        elif return_fit:
            return weights, fitted_spectrum
        else:
            return weights

    def fit_map(self, spectrum, **kwargs):
        """
        """

        # TODO remove

        values = self.fit(spectrum, **kwargs)

        return self.map(values)

    @property
    def measured_spectra(self):
        return self._container

    @property
    def _measured_spectra(self):
        return self._container

    @property
    def _ylabel(self):
        return self[0]._ylabel
