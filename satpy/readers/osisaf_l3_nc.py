#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2023 Satpy developers
#
# This file is part of satpy.
#
# satpy is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# satpy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# satpy.  If not, see <http://www.gnu.org/licenses/>.
# type: ignore
"""A reader for OSI-SAF level 3 products in netCDF format."""

import logging
from datetime import datetime

import numpy as np

from satpy.readers.netcdf_utils import NetCDF4FileHandler

logger = logging.getLogger(__name__)


class OSISAFL3NCFileHandler(NetCDF4FileHandler):
    """Reader for the OSISAF l3 netCDF format."""

    @staticmethod
    def _parse_datetime(datestr):
        return datetime.strptime(datestr, "%Y-%m-%d %H:%M:%S")

    def _get_ease_grid(self):
        """Set up the EASE grid."""
        from pyresample import create_area_def

        proj4str = self["Lambert_Azimuthal_Grid/attr/proj4_string"]
        x_size = self["/dimension/xc"]
        y_size = self["/dimension/yc"]
        p_lowerleft_lat = self["lat"].values[y_size - 1, 0]
        p_lowerleft_lon = self["lon"].values[y_size - 1, 0]
        p_upperright_lat = self["lat"].values[0, x_size - 1]
        p_upperright_lon = self["lon"].values[0, x_size - 1]
        area_extent = [p_lowerleft_lon, p_lowerleft_lat, p_upperright_lon, p_upperright_lat]
        area_def = create_area_def(area_id="osisaf_lambert_azimuthal_equal_area",
                                   description="osisaf_lambert_azimuthal_equal_area",
                                   proj_id="osisaf_lambert_azimuthal_equal_area",
                                   projection=proj4str, width=x_size, height=y_size, area_extent=area_extent,
                                   units="deg")
        return area_def

    def _get_polar_stereographic_grid(self):
        """Set up the polar stereographic grid."""
        from pyresample import create_area_def

        proj4str = self["Polar_Stereographic_Grid/attr/proj4_string"]
        x_size = self["/dimension/xc"]
        y_size = self["/dimension/yc"]
        p_lowerleft_lat = self["lat"].values[y_size - 1, 0]
        p_lowerleft_lon = self["lon"].values[y_size - 1, 0]
        p_upperright_lat = self["lat"].values[0, x_size - 1]
        p_upperright_lon = self["lon"].values[0, x_size - 1]
        area_extent = [p_lowerleft_lon, p_lowerleft_lat, p_upperright_lon, p_upperright_lat]
        area_def = create_area_def(area_id="osisaf_polar_stereographic",
                                   description="osisaf_polar_stereographic",
                                   proj_id="osisaf_polar_stereographic",
                                   projection=proj4str, width=x_size, height=y_size, area_extent=area_extent,
                                   units="deg")
        return area_def


    def get_area_def(self, area_id):
        """Override abstract baseclass method"""
        if self.filename_info["grid"] == "ease":
            self.area_def = self._get_ease_grid()
            return self.area_def
        elif self.filename_info["grid"] == "polstere" or self.filename_info["grid"] == "stere":
            self.area_def = self._get_polar_stereographic_grid()
            return self.area_def
        else:
            raise ValueError(f"Unknown grid type: {self.filename_info['grid']}")

    def _get_ds_attr(self, a_name):
        """Get a dataset attribute and check it's valid."""
        try:
            return self[a_name]
        except KeyError:
            return None

    def get_dataset(self, dataset_id, ds_info):
        """Load a dataset."""
        logger.debug(f"Reading {dataset_id['name']} from {self.filename}")
        var_path = ds_info.get("file_key", f"{dataset_id['name']}")

        shape = self[var_path + "/shape"]
        if shape[0] == 1:
            # Remove the time dimension from dataset
            data = self[var_path][0]
        else:
            data = self[var_path]

        file_units = ds_info.get("file_units")
        if file_units is None:
            file_units = self._get_ds_attr(var_path + "/attr/units")
            if file_units is None:
                file_units = 1

        # Try to get the valid limits for the data.
        # Not all datasets have these, so fall back on assuming no limits.
        valid_min = self._get_ds_attr(var_path + "/attr/valid_min")
        valid_max = self._get_ds_attr(var_path + "/attr/valid_max")
        if valid_min is not None and valid_max is not None:
            data = data.where(data >= valid_min, np.nan)
            data = data.where(data <= valid_max, np.nan)

        # Try to get the scale and offset for the data.
        # As above, not all datasets have these, so fall back on assuming no limits.
        scale_factor = self._get_ds_attr(var_path + "/attr/scale_factor")
        scale_offset = self._get_ds_attr(var_path + "/attr/add_offset")
        if scale_offset is not None and scale_factor is not None:
            data = (data * scale_factor + scale_offset)

        # Try to get the fill value for the data.
        # If there isn't one, assume all remaining pixels are valid.
        fill_value = self._get_ds_attr(var_path + "/attr/_FillValue")
        if fill_value is not None:
            data = data.where(data != fill_value, np.nan)

        # Set proper dimension names
        data = data.rename({"xc": "x", "yc": "y"})

        ds_info.update({
            "units": ds_info.get("units", file_units),
            "platform_name": self["/attr/platform_name"],
            "sensor": self["/attr/instrument_type"]
        })
        ds_info.update(dataset_id.to_dict())
        data.attrs.update(ds_info)
        return data

    @property
    def start_time(self):
        return self._parse_datetime(self["/attr/start_date"])
        # return self._parse_datetime(self["/attr/start_date"])

    @property
    def end_time(self):
        return self._parse_datetime(self["/attr/stop_date"])
