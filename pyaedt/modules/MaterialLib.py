# -*- coding: utf-8 -*-
"""
This module contains the `Materials` class.
"""
from __future__ import absolute_import  # noreorder

import copy
import fnmatch
import json
import os
import re

from pyaedt import settings
from pyaedt.generic.DataHandlers import _arg2dict
from pyaedt.generic.general_methods import _create_json_file
from pyaedt.generic.general_methods import _retry_ntimes
from pyaedt.generic.general_methods import generate_unique_name
from pyaedt.generic.general_methods import open_file
from pyaedt.generic.general_methods import pyaedt_function_handler
from pyaedt.modules.Material import Material
from pyaedt.modules.Material import MatProperties
from pyaedt.modules.Material import OrderedDict
from pyaedt.modules.Material import SurfaceMaterial


class Materials(object):
    """Contains the AEDT materials database and all methods for creating and editing materials.

    Parameters
    ----------
    app : :class:`pyaedt.application.Analysis3D.FieldAnalysis3D`
        Inherited parent object.

    Examples
    --------
    >>> from pyaedt import Hfss
    >>> app = Hfss()
    >>> materials = app.materials
    """

    def __init__(self, app):
        self._app = app
        self._color_id = 0
        self.odefinition_manager = self._app.odefinition_manager
        self.omaterial_manager = self._app.omaterial_manager
        self._mats = []
        self._mats_lower = []
        self._desktop = self._app.odesktop
        self._oproject = self._app.oproject
        self.logger = self._app.logger
        self.logger.info("Successfully loaded project materials !")
        # self.material_keys = self._get_materials()
        self.material_keys = {}
        self._surface_material_keys = {}
        self._load_from_project()
        pass

    def __len__(self):
        return len(self.material_keys)

    def __iter__(self):
        return self.material_keys.itervalues()

    def __getitem__(self, item):
        matobj = self.checkifmaterialexists(item)
        if matobj:
            return matobj
        elif item in list(self.surface_material_keys.keys()):
            return self.surface_material_keys[item]
        return

    @property
    def surface_material_keys(self):
        """Dictionary of Surface Material in the project.

        Returns
        -------
        dict of :class:`pyaedt.modules.Material.Material`
        """
        if not self._surface_material_keys:
            self._surface_material_keys = self._get_surface_materials()
        return self._surface_material_keys

    @property
    def liquids(self):
        """Return the liquids materials. A liquid is a fluid with density greater or equal to 100Kg/m3.

        Returns
        -------
        list
            List of fluid materials.
        """
        mats = []
        for el, val in self.material_keys.items():
            if val.thermal_material_type == "Fluid" and val.mass_density.value and float(val.mass_density.value) >= 100:
                mats.append(el)
        return mats

    @property
    def gases(self):
        """Return the gas materials. A gas is a fluid with density lower than 100Kg/m3.

        Returns
        -------
        list
            List of all Gas materials.
        """
        mats = []
        for el, val in self.material_keys.items():
            if val.thermal_material_type == "Fluid" and val.mass_density.value and float(val.mass_density.value) < 100:
                mats.append(el)
        return mats

    @property
    def _mat_names_aedt(self):
        if not self._mats:
            self._mats = self._read_materials()
        return self._mats

    @property
    def _mat_names_aedt_lower(self):
        if len(self._mats_lower) < len(self._mat_names_aedt):
            self._mats_lower = [i.lower() for i in self._mat_names_aedt]
        return self._mats_lower

    @pyaedt_function_handler()
    def _read_materials(self):
        def get_mat_list(file_name):
            mats = []
            _begin_search = re.compile(r"^\$begin '(.+)'")
            with open_file(file_name, "r") as aedt_fh:
                raw_lines = aedt_fh.read().splitlines()
                for line in raw_lines:
                    b = _begin_search.search(line)
                    if b:  # walk down a level
                        mats.append(b.group(1))
            return mats

        amat_sys = [
            os.path.join(dirpath, filename)
            for dirpath, _, filenames in os.walk(self._app.syslib)
            for filename in filenames
            if fnmatch.fnmatch(filename, "*.amat")
        ]
        amat_personal = [
            os.path.join(dirpath, filename)
            for dirpath, _, filenames in os.walk(self._app.personallib)
            for filename in filenames
            if fnmatch.fnmatch(filename, "*.amat")
        ]
        amat_user = [
            os.path.join(dirpath, filename)
            for dirpath, _, filenames in os.walk(self._app.userlib)
            for filename in filenames
            if fnmatch.fnmatch(filename, "*.amat")
        ]
        amat_libs = amat_sys + amat_personal + amat_user
        mats = []
        for amat in amat_libs:
            # m = load_entire_aedt_file(amat)
            # mats.extend(list(m.keys()))
            mats.extend(get_mat_list(amat))
        try:
            mats.remove("$index$")
        except ValueError:
            pass
        try:
            mats.remove("$base_index$")
        except ValueError:
            pass
        mats.extend(self.odefinition_manager.GetProjectMaterialNames())
        return mats

    @pyaedt_function_handler()
    def _get_aedt_case_name(self, material_name):
        if material_name.lower() in self.material_keys:
            return self.material_keys[material_name.lower()].name
        if material_name.lower() in self._mat_names_aedt_lower:
            return self._mat_names_aedt[self._mat_names_aedt_lower.index(material_name.lower())]
        return False

    @pyaedt_function_handler()
    def _get_materials(self):
        """Get materials."""
        mats = {}
        try:
            for ds in self._app.project_properties["AnsoftProject"]["Definitions"]["Materials"]:
                mats[ds.lower()] = Material(
                    self, ds, self._app.project_properties["AnsoftProject"]["Definitions"]["Materials"][ds]
                )
        except:
            pass
        return mats

    @pyaedt_function_handler()
    def _get_surface_materials(self):
        mats = {}
        try:
            for ds in self._app.project_properties["AnsoftProject"]["Definitions"]["SurfaceMaterials"]:
                mats[ds.lower()] = SurfaceMaterial(
                    self,
                    ds,
                    self._app.project_properties["AnsoftProject"]["Definitions"]["SurfaceMaterials"][ds],
                )
        except:
            pass
        return mats

    @pyaedt_function_handler()
    def checkifmaterialexists(self, mat):
        """Check if a material exists in AEDT or PyAEDT Definitions.

        Parameters
        ----------
        mat : str
            Name of the material. If the material exists and is not in the materials database,
            it is added to this database.

        Returns
        -------
        :class:`pyaedt.modules.Material.Material`
            Material object if present, ``False`` when failed.

        References
        ----------

        >>> oDefinitionManager.GetProjectMaterialNames
        >>> oMaterialManager.GetData
        """
        if isinstance(mat, Material):
            if mat.name.lower() in self.material_keys:
                return mat
            else:
                return False
        if mat.lower() in self.material_keys:
            if mat.lower() in self._mat_names_aedt_lower:
                return self.material_keys[mat.lower()]
            if mat.lower() not in list(self.odefinition_manager.GetProjectMaterialNames()):
                self.material_keys[mat.lower()].update()
            return self.material_keys[mat.lower()]
        elif mat.lower() in self._mat_names_aedt_lower:
            return self._aedmattolibrary(mat)
        elif settings.remote_api:
            return self._aedmattolibrary(mat)
        return False

    @pyaedt_function_handler()
    def check_thermal_modifier(self, mat):
        """Check a material to see if it has any thermal modifiers.

        Parameters
        ----------
        mat : str
            Name of the material. All properties for this material are checked
            for thermal modifiers.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed.

        """
        omat = self.checkifmaterialexists(mat)
        if omat:
            for el in MatProperties.aedtname:
                if omat.__dict__["_" + el].thermalmodifier:
                    return True
        return False

    @pyaedt_function_handler()
    def add_material(self, materialname, props=None):
        """Add a material with default values.

        When the added material object is returned, you can customize
        the material. This method does not update the material.

        Parameters
        ----------
        materialname : str
            Name of the material.
        props : dict, optional
            Material property dictionary. The default is ``None``.

        Returns
        -------
        :class:`pyaedt.modules.Material.Material`

        References
        ----------

        >>> oDefinitionManager.AddMaterial

        Examples
        --------

        >>> from pyaedt import Hfss
        >>> hfss = Hfss()
        >>> mat = hfss.materials.add_material("MyMaterial")
        >>> print(mat.conductivity.value)

        >>> oDefinitionManager.GetProjectMaterialNames
        >>> oMaterialManager.GetData

        """
        materialname = materialname
        self.logger.info("Adding new material to the Project Library: " + materialname)
        if materialname.lower() in self.material_keys:
            self.logger.warning("Warning. The material is already in the database. Change or edit the name.")
            return self.material_keys[materialname.lower()]
        elif self._get_aedt_case_name(materialname):
            return self._aedmattolibrary(self._get_aedt_case_name(materialname))
        else:
            material = Material(self, materialname, props)
            if material.update():
                self.logger.info("Material has been added. Edit it to update in Desktop.")
                self.material_keys[materialname.lower()] = material
                self._mats.append(materialname)
                return self.material_keys[materialname.lower()]
        return False

    @pyaedt_function_handler()
    def add_surface_material(self, material_name, emissivity=None):
        """Add a surface material.

        In AEDT, base properties are loaded from the XML database file ``amat.xml``
        or from the emissivity.

        Parameters
        ----------
        material_name : str
            Name of the surface material.
        emissivity : float, optional
            Emissivity value.

        Returns
        -------
        :class:`pyaedt.modules.SurfaceMaterial`

        References
        ----------

        >>> oDefinitionManager.AddSurfaceMaterial

        Examples
        --------

        >>> from pyaedt import Hfss
        >>> hfss = Hfss()
        >>> mat = hfss.materials.add_surface_material("Steel", 0.85)
        >>> print(mat.emissivity.value)

        """
        self.logger.info("Adding a surface material to the project library: " + material_name)
        if material_name.lower() in self.surface_material_keys:
            self.logger.warning("Warning. The material is already in the database. Change the name or edit it.")
            return self.surface_material_keys[material_name.lower()]
        else:
            material = SurfaceMaterial(self._app, material_name)
            if emissivity:
                material.emissivity = emissivity
                material.update()
            self.logger.info("Material has been added. Edit it to update in Desktop.")
            self.surface_material_keys[material_name.lower()] = material
            return self.surface_material_keys[material_name.lower()]

    @pyaedt_function_handler()
    def _create_mat_project_vars(self, matlist):
        matprop = {}
        tol = 1e-12
        for prop in MatProperties.aedtname:
            matprop[prop] = []
            for mat in matlist:
                try:
                    matprop[prop].append(float(mat.__dict__["_" + prop].value))
                except:
                    self.logger.warning("Warning. Wrong parsed property. Reset to 0")
                    matprop[prop].append(0)
            try:
                a = sum(matprop[prop])
                if a < tol:
                    del matprop[prop]
            except:
                pass
        return matprop

    @pyaedt_function_handler()
    def add_material_sweep(self, swargs, matname):
        """Create a sweep material made of an array of materials.

        If a material needs to have a dataset (thermal modifier), then a
        dataset is created. Material properties are loaded from the XML file
        database ``amat.xml``.

        Parameters
        ----------
        swargs : list
            List of materials to merge into a single sweep material.
        matname : str
            Name of the sweep material.
        enableTM : bool, optional
            Unavailable currently. Whether to enable the thermal modifier.
            The default is ``True``.

        Returns
        -------
        int
            Index of the project variable.

        References
        ----------

        >>> oDefinitionManager.AddMaterial

        Examples
        --------

        >>> from pyaedt import Hfss
        >>> hfss = Hfss()
        >>> hfss.materials.add_material("MyMaterial")
        >>> hfss.materials.add_material("MyMaterial2")
        >>> hfss.materials.add_material_sweep(["MyMaterial", "MyMaterial2"], "Sweep_copper")
        """
        matsweep = []
        for args in swargs:
            matobj = self.checkifmaterialexists(args)
            if matobj:
                matsweep.append(matobj)

        mat_dict = self._create_mat_project_vars(matsweep)

        newmat = Material(self, matname)
        index = "$ID" + matname
        newmat.is_sweep_material = True
        self._app[index] = 0
        for el in mat_dict:
            if el in list(mat_dict.keys()):
                self._app["$" + matname + el] = mat_dict[el]
                newmat.__dict__["_" + el].value = "$" + matname + el + "[" + index + "]"
                newmat._update_props(el, "$" + matname + el + "[" + index + "]", False)

        newmat.update()
        self.material_keys[matname.lower()] = newmat
        return index

    @pyaedt_function_handler()
    def duplicate_material(self, material, new_name):
        """Duplicate a material.

        Parameters
        ----------
        material : str
            Name of the material.
        new_name : str
            Name for the copy of the material.

        Returns
        -------
        :class:`pyaedt.modules.Material.Material`

        References
        ----------

        >>> oDefinitionManager.AddMaterial

        Examples
        --------

        >>> from pyaedt import Hfss
        >>> hfss = Hfss()
        >>> hfss.materials.add_material("MyMaterial")
        >>> hfss.materials.duplicate_material("MyMaterial", "MyMaterial2")

        """
        if material.lower() not in list(self.material_keys.keys()):
            self.logger.error("Material {} is not present".format(material))
            return False
        if material.lower() not in list(self.material_keys.keys()):
            matobj = self._aedmattolibrary(material)
        else:
            matobj = self.material_keys[material.lower()]

        newmat = Material(self, new_name, matobj._props)
        newmat.update()
        self._mats.append(new_name)
        self.material_keys[new_name.lower()] = newmat
        return newmat

    @pyaedt_function_handler()
    def duplicate_surface_material(self, material, new_name):
        """Duplicate a surface material.

        Parameters
        ----------
         material : str
            Name of the surface material.
        new_name : str
            Name for the copy of the surface material.

        Returns
        -------
        :class:`pyaedt.modules.SurfaceMaterial`

        References
        ----------

        >>> oDefinitionManager.AddSurfaceMaterial

        Examples
        --------

        >>> from pyaedt import Hfss
        >>> hfss = Hfss()
        >>> hfss.materials.add_surface_material("MyMaterial")
        >>> hfss.materials.duplicate_surface_material("MyMaterial", "MyMaterial2")
        """
        if not material.lower() in list(self.surface_material_keys.keys()):
            self.logger.error("Material {} is not present".format(material))
            return False
        newmat = SurfaceMaterial(self, new_name.lower(), self.surface_material_keys[material.lower()]._props)
        newmat.update()
        self.surface_material_keys[new_name.lower()] = newmat
        return newmat

    @pyaedt_function_handler()
    def remove_material(self, material, library="Project"):
        """Remove a material.

        Parameters
        ----------
        material : str
            Name of the material.
        library : str, optional
            Name of the library containing this material.
            The default is ``"Project"``.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed.

        References
        ----------

        >>> oDefinitionManager.RemoveMaterial

        Examples
        --------

        >>> from pyaedt import Hfss
        >>> hfss = Hfss()
        >>> hfss.materials.add_material("MyMaterial")
        >>> hfss.materials.remove_material("MyMaterial")

        """
        mat = material.lower()
        if mat not in list(self.material_keys.keys()):
            self.logger.error("Material {} is not present".format(mat))
            return False
        self.odefinition_manager.RemoveMaterial(self._get_aedt_case_name(mat), True, "", library)
        del self.material_keys[mat]
        return True

    @property
    def conductors(self):
        """Conductors in the material database.

        Returns
        -------
        list
            List of conductors in the material database.

        """
        data = []
        for key, mat in self.material_keys.items():
            if mat.is_conductor():
                data.append(key)
        return data

    @property
    def dielectrics(self):
        """Dielectrics in the material database.

        Returns
        -------
        list
            List of dielectrics in the material database.

        """
        data = []
        for key, mat in self.material_keys.items():
            if mat.is_dielectric():
                data.append(key)
        return data

    def _load_from_project(self):
        if self.odefinition_manager:
            mats = self.odefinition_manager.GetProjectMaterialNames()
            for el in mats:
                if el not in list(self.material_keys.keys()):
                    try:
                        self._aedmattolibrary(el)
                    except Exception as e:
                        self.logger.info("aedmattolibrary failed for material %s", el)

    @pyaedt_function_handler()
    def _aedmattolibrary(self, matname):
        """Get and convert Material Properties from AEDT to Dictionary.

        Parameters
        ----------
        matname : str

        Returns
        -------
        :class:`pyaedt.modules.Material.Material`
        """
        if matname not in self.odefinition_manager.GetProjectMaterialNames() and not settings.remote_api:
            matname = self._get_aedt_case_name(matname)
        props = {}
        _arg2dict(list(_retry_ntimes(20, self.omaterial_manager.GetData, matname)), props)
        values_view = props.values()
        value_iterator = iter(values_view)
        first_value = next(value_iterator)
        newmat = Material(self, matname, first_value)
        self.material_keys[matname.lower()] = newmat
        return self.material_keys[matname.lower()]

    @pyaedt_function_handler()
    def export_materials_to_file(self, full_json_path):
        """Export all materials to a JSON file.

        Parameters
        ----------
        full_json_path : str
            Full path and name of the JSON file to export to.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed.

        """

        def find_datasets(d, out_list):
            for k, v in d.items():
                if isinstance(v, (dict, OrderedDict)):
                    find_datasets(v, out_list)
                else:
                    a = copy.deepcopy(v)
                    val = a
                    if str(type(a)) == r"<type 'List'>":
                        val = list(a)
                    if "pwl(" in str(val) or "cpl(" in str(val):
                        if isinstance(a, list):
                            for element in a:
                                m = re.search(r"(?:pwl|cwl)\((.*?),", str(element))
                                if m:
                                    out_list.append(m.group(1))
                        else:
                            out_list.append(a[a.find("$") : a.find(",")])

        # Data to be written
        output_dict = {}
        for el, val in self.material_keys.items():
            output_dict[el] = copy.deepcopy(val._props)
        out_list = []
        find_datasets(output_dict, out_list)
        datasets = OrderedDict()
        for ds in out_list:
            if ds in list(self._app.project_datasets.keys()):
                d = self._app.project_datasets[ds]
                if d.z:
                    datasets[ds] = OrderedDict(
                        {
                            "Coordinates": OrderedDict(
                                {
                                    "DimUnits": [d.xunit, d.yunit, d.zunit],
                                    "Points": [val for tup in zip(d.x, d.y, d.z) for val in tup],
                                }
                            )
                        }
                    )
                else:
                    datasets[ds] = OrderedDict(
                        {
                            "Coordinates": OrderedDict(
                                {
                                    "DimUnits": [d.xunit, d.yunit],
                                    "Points": [val for tup in zip(d.x, d.y) for val in tup],
                                }
                            )
                        }
                    )
        json_dict = {}
        json_dict["materials"] = output_dict
        if datasets:
            json_dict["datasets"] = datasets
        return _create_json_file(json_dict, full_json_path)

    @pyaedt_function_handler()
    def import_materials_from_file(self, full_json_path):
        """Import and create materials from a JSON file.

        Parameters
        ----------
        full_json_path : str
            Full path and name for the JSON file.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed.

        """
        with open_file(full_json_path, "r") as json_file:
            data = json.load(json_file)

        if "datasets" in list(data.keys()):
            for el, val in data["datasets"].items():
                numcol = len(val["Coordinates"]["DimUnits"])
                xunit = val["Coordinates"]["DimUnits"][0]
                yunit = val["Coordinates"]["DimUnits"][1]
                zunit = ""

                new_list = [
                    val["Coordinates"]["Points"][i : i + numcol]
                    for i in range(0, len(val["Coordinates"]["Points"]), numcol)
                ]
                xval = new_list[0]
                yval = new_list[1]
                zval = None
                if numcol > 2:
                    zunit = val["Coordinates"]["DimUnits"][2]
                    zval = new_list[2]
                self._app.create_dataset(
                    el[1:], xunit=xunit, yunit=yunit, zunit=zunit, xlist=xval, ylist=yval, zlist=zval
                )

        for el, val in data["materials"].items():
            if el.lower() in list(self.material_keys.keys()):
                newname = generate_unique_name(el)
                self.logger.warning("Material %s already exists. Renaming to %s", el, newname)
            else:
                newname = el
            newmat = Material(self, newname, val)
            newmat.update()
            self.material_keys[newname] = newmat
        return True
