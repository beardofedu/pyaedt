"""
This module contains these Primitives classes: `Polyline` and `Primitives`.
"""
from __future__ import absolute_import  # noreorder

import copy
import math
import os
import time
from collections import OrderedDict

from pyaedt.application.Variables import Variable
from pyaedt.generic.constants import PLANE
from pyaedt.generic.general_methods import _retry_ntimes
from pyaedt.generic.general_methods import is_number
from pyaedt.generic.general_methods import pyaedt_function_handler
from pyaedt.modeler.GeometryOperators import GeometryOperators
from pyaedt.modeler.Object3d import EdgePrimitive
from pyaedt.modeler.Object3d import FacePrimitive
from pyaedt.modeler.Object3d import Object3d
from pyaedt.modeler.Object3d import UserDefinedComponent
from pyaedt.modeler.Object3d import _dim_arg
from pyaedt.modeler.Object3d import _uname
from pyaedt.modeler.object3dlayout import Point
from pyaedt.modules.MaterialLib import Material

default_materials = {
    "Icepak": "air",
    "HFSS": "vacuum",
    "Maxwell 3D": "vacuum",
    "Maxwell 2D": "vacuum",
    "2D Extractor": "copper",
    "Q3D Extractor": "copper",
    "HFSS 3D Layout": "copper",
    "Mechanical": "copper",
}

aedt_wait_time = 0.1


class PolylineSegment:
    """Creates and manipulates a segment of a polyline.

    Parameters
    ----------
    type : str
        Type of the object. Choices are ``"Line"``, ``"Arc"``, ``"Spline"``,
        and ``"AngularArc"``.
    num_seg : int, optional
        Number of segments for the types ``"Arc"``, ``"Spline"``, and
        ``"AngularArc"``.  The default is ``0``. For the type
        ``Line``, this parameter is ignored.
    num_points : int, optional
        Number of control points for the type ``Spline``. For other
        types, this parameter
        is defined automatically.
    arc_angle : float or str, optional
        Sweep angle in radians or a valid value string. For example,
        ``"35deg"`` or ``"Specific
        to type AngularArc"``.
    arc_center : list or str, optional
        List of values in model units or a valid value string. For
        example, a list of ``[x, y, z]`` coordinates or ``"Specific to
        type AngularArc"``.
    arc_plane : str, int optional
        Plane in which the arc sweep is performed in the active
        coordinate system ``"XY"``, ``"YZ"`` or ``"ZX"``. The default is
        ``None``, in which case the plane is determined automatically
        by the first coordinate for which the starting point and
        center point have the same value.

    Examples
    --------
    See :class:`pyaedt.Primitives.Polyline`.

    """

    def __init__(self, type, num_seg=0, num_points=0, arc_angle=0, arc_center=None, arc_plane=None):

        valid_types = ["Line", "Arc", "Spline", "AngularArc"]
        assert type in valid_types, "Segment type must be in {}.".format(valid_types)
        self.type = type
        if type != "Line":
            self.num_seg = num_seg
        if type == "Line":
            self.num_points = 2
        if type == "Spline":
            self.num_points = num_points
        if "Arc" in type:
            self.num_points = 3
        if type == "AngularArc":
            self.arc_angle = arc_angle
            if not arc_center:
                arc_center = [0, 0, 0]
            assert len(arc_center) == 3, "Arc center must be a list of length 3."
            self.arc_center = arc_center
        if isinstance(arc_plane, int):
            if arc_plane == PLANE.XY:
                self.arc_plane = "XY"
            elif arc_plane == PLANE.ZX:
                self.arc_plane = "ZX"
            else:
                self.arc_plane = "YZ"
        else:
            self.arc_plane = arc_plane


class Polyline(Object3d):
    """Creates and manipulates a polyline.

    The constructor for this class is intended to be called from the
    :func:`pyaedt.modeler.Primitives.Primitives.create_polyline` method.
    The documentation is provided there.

    The returned Polyline object exposes the methods for manipulating the polyline.

    Parameters
    ----------
    primitives : :class:`pyaedt.modeler.Primitives3D.Primitives3D`
        Pointer to the parent Primitives object.
    src_object : optional
        The default is ``None``.
    position_list : list, optional
        List of positions in the ``[x, y, z]`` format. The default is ``None``.
    segment_type : str or list, optional
        Define the list of segment types.
        Valid arguments are  ``"Line"``, ``"Arc"``, ``"Spline"``, ``"AngularArc"``.
        The default is ``None``.
    cover_surface : bool, optional
        The default is ``False``.
    close_surface : bool, optional
        The default is ``False``.
    name : str, optional
        The default is ``None``.
    matname : str, optional
        Name of the material. The default is ``None``.
    xsection_type : str, optional
        Type of the cross-section. Options are ``"Line"``, ``"Circle"``, ``"Rectangle"``,
        and ``"Isosceles Trapezoid"``. The default is ``None``.
    xsection_orient : str, optional
        Direction of the normal vector to the width of the cross-section.
        Options are ``"X"``, ``"Y"``, ``"Z"``, and ``"Auto"``. The
        default is ``None``.
    xsection_width : float or str, optional
        Width or diameter of the cross-section for all types. The default is
        ``1``.
    xsection_topwidth : float or str, optional
        Top width of the cross-section for the type ``"Isosceles Trapezoid"`` only.
        The default is ``1``.
    xsection_height : float or str, optional
        Height of the cross-section for the types ``"Rectangle"`` and ``"Isosceles
        Trapezoid"`` only. The default is ``1``.
    xsection_num_seg : int, optional
        Number of segments in the cross-section surface for the types ``"Circle"``,
        ``"Rectangle"`` and ``"Isosceles Trapezoid"``. The default is ``0``.
        The value must be ``0`` or greater than ``2``.
    xsection_bend_type : str, optional
        Type of the bend. The default is ``None``, in which case the bend type
        is set to ``"Corner"``. For the type ``"Circle"``, the bend type
        should be set to ``"Curved"``.

    """

    def __init__(
        self,
        primitives,
        src_object=None,
        position_list=None,
        segment_type=None,
        cover_surface=False,
        close_surface=False,
        name=None,
        matname=None,
        xsection_type=None,
        xsection_orient=None,
        xsection_width=1,
        xsection_topwidth=1,
        xsection_height=1,
        xsection_num_seg=0,
        xsection_bend_type=None,
        non_model=False,
    ):

        self._primitives = primitives

        if src_object:
            self.__dict__ = src_object.__dict__.copy()
            if name:
                self._m_name = name  # This is conimg from
            else:
                self._id = src_object.id
                self._m_name = src_object.name
        else:

            self._xsection = self._primitives._crosssection_arguments(
                type=xsection_type,
                orient=xsection_orient,
                width=xsection_width,
                topwidth=xsection_topwidth,
                height=xsection_height,
                num_seg=xsection_num_seg,
                bend_type=xsection_bend_type,
            )
            self._positions = [i for i in position_list]
            # When close surface or cover_surface are set to True, ensure the start point and end point are coincident,
            # and insert a line segment to achieve this if necessary
            if cover_surface:
                close_surface = True

            self._is_closed = close_surface
            self._is_covered = cover_surface

            self._segment_types = None
            if segment_type:
                if isinstance(segment_type, (list, tuple)):
                    # self._segment_types = copy(segment_type)
                    self._segment_types = [i for i in segment_type]
                else:
                    self._segment_types = segment_type

            varg1 = self._point_segment_string_array()
            if non_model:
                flag = "NonModel#"
            else:
                flag = ""
            varg2 = self._primitives._default_object_attributes(name=name, matname=matname, flags=flag)

            new_object_name = _retry_ntimes(10, self.m_Editor.CreatePolyline, varg1, varg2)

            Object3d.__init__(self, primitives, name=new_object_name)
            self._primitives.objects[self.id] = self
            self._primitives.object_id_dict[self.name] = self.id

    @property
    def start_point(self):
        """List of the ``[x, y, z]`` coordinates for the starting point in the polyline
        object in the object's coordinate system.

        Returns
        -------
        list
            List of the ``[x, y, z]`` coordinates for the starting point in the polyline
            object.

        """
        return self.vertices[0].position

    @property
    def end_point(self):
        """List of the ``[x, y, z]`` coordinates for the ending point in the polyline
        object in the object's coordinate system.

        Returns
        -------
        list
            List of the ``[x, y, z]`` coordinates for the ending point in the polyline
            object.

        References
        ----------

        >>> oEditor.GetVertexIDsFromObject
        >>> oEditor.GetVertexPosition

        """
        return self.vertices[-1].position

    @property
    def points(self):
        """Polyline Points."""
        return self._positions

    @property
    def vertex_positions(self):
        """List of the ``[x, y, z]`` coordinates for all vertex positions in the
        polyline object in the object's coordinate system.

        Returns
        -------
        list
            List of the ``[x, y, z]`` coordinates for all vertex positions in the
            polyline object.

        References
        ----------

        >>> oEditor.GetVertexIDsFromObject
        >>> oEditor.GetVertexPosition

        """
        id_list = self._primitives.get_object_vertices(partID=self.id)
        position_list = [self._primitives.get_vertex_position(id) for id in id_list]
        return position_list

    @pyaedt_function_handler()
    def _pl_point(self, pt):
        pt_data = ["NAME:PLPoint"]
        pt_data.append("X:=")
        pt_data.append(_dim_arg(pt[0], self._primitives.model_units))
        pt_data.append("Y:=")
        pt_data.append(_dim_arg(pt[1], self._primitives.model_units))
        pt_data.append("Z:=")
        pt_data.append(_dim_arg(pt[2], self._primitives.model_units))
        return pt_data

    @pyaedt_function_handler()
    def _point_segment_string_array(self):
        """Retrieve the parameter arrays for specifying the points and segments of a polyline
        used in the :class:`pyaedt.modeler.Primitives.Polyline` constructor.

        Returns
        -------
        list

        """
        position_list = self._positions
        segment_types = self._segment_types

        assert (
            len(position_list) > 0
        ), "The ``position_list`` argument must be a list of positions with at least one point."
        if not segment_types:
            segment_types = [PolylineSegment("Line")] * (len(position_list) - 1)
        elif isinstance(segment_types, str):
            segment_types = [PolylineSegment(segment_types, num_points=len(position_list))]
        elif isinstance(segment_types, PolylineSegment):
            segment_types = [segment_types]
        elif isinstance(segment_types, list):
            # Convert all string-type entries in the segment_types list to PolylineSegments
            for ind, seg in enumerate(segment_types):
                if isinstance(seg, str):
                    segment_types[ind] = PolylineSegment(seg)
        else:
            raise ("Invalid segment_types input of type {}".format(type(segment_types)))

        # Add a closing point if needed  #TODO check for all combinations
        varg1 = ["NAME:PolylineParameters"]
        varg1.append("IsPolylineCovered:=")
        varg1.append(self._is_covered)
        varg1.append("IsPolylineClosed:=")
        varg1.append(self._is_closed)

        # PointsArray
        points_str = ["NAME:PolylinePoints"]
        points_str.append(self._pl_point(position_list[0]))

        # Segments Array
        segment_str = ["NAME:PolylineSegments"]

        pos_count = 0
        vertex_count = 0
        index_count = 0

        while vertex_count <= len(segment_types):
            try:
                current_segment = None
                if vertex_count == len(segment_types):
                    if self._is_closed:
                        # Check the special case of a closed polyline needing an additional Line segment
                        if position_list[0] != position_list[-1]:
                            position_list.append(position_list[0])
                            current_segment = PolylineSegment("Line")
                    else:
                        break
                else:
                    current_segment = segment_types[vertex_count]
            except IndexError:
                raise ("Number of segments inconsistent with the number of points!")

            if current_segment:
                seg_str = self._segment_array(
                    current_segment, start_index=index_count, start_point=position_list[pos_count]
                )
                segment_str.append(seg_str)

                pos_count_incr = 0
                for i in range(1, current_segment.num_points):

                    if current_segment.type == "AngularArc":
                        points_str.append(self._pl_point(current_segment.extra_points[i - 1]))
                        index_count += 1
                    else:
                        if (pos_count + i) == len(position_list):
                            if current_segment.type == "Arc" and self._is_closed:
                                position_list.append(position_list[0])
                            else:
                                err_str = "Insufficient points in position_list to complete the specified segment list"
                                raise IndexError(err_str)
                        points_str.append(self._pl_point(position_list[pos_count + i]))
                        pos_count_incr += 1
                        index_count += 1
                pos_count += pos_count_incr
                vertex_count += 1
            else:
                break

        varg1.append(points_str)
        varg1.append(segment_str)

        # Poly Line Cross Section
        varg1.append(self._xsection)

        return varg1

    @pyaedt_function_handler()
    def _segment_array(self, segment_data, start_index=0, start_point=None):
        """Retrieve a property array for a polyline segment for use in the
        :class:`pyaedt.modeler.Primitives.Polyline` constructor.

         Parameters
         ----------
         segment_data : :class:`pyaedt.modeler.Primitives.PolylineSegment` or str
             Pointer to the calling object that provides additional functionality
             or a string with the segment type ``Line`` or ``Arc``.
         start_index : int, string
             Starting vertex index of the segment within a compound polyline. The
             default is ``0``.
         start_point : list, optional
             Position of the first point for type ``AngularArc``. The default is
             ``None``. Float values are considered in model units.

         Returns
         ------
         list
             List of properties defining a polyline segment.

        """
        if isinstance(segment_data, str):
            segment_data = PolylineSegment(segment_data)

        seg = [
            "NAME:PLSegment",
            "SegmentType:=",
            segment_data.type,
            "StartIndex:=",
            start_index,
            "NoOfPoints:=",
            segment_data.num_points,
        ]
        if segment_data.type != "Line":
            seg += ["NoOfSegments:=", "{}".format(segment_data.num_seg)]

        if segment_data.type == "AngularArc":

            # from start-point and angle, calculate the mid- and end-points
            # Also identify the plane of the arc ("YZ", "ZX", "XY")
            plane_axes = {"YZ": [1, 2], "ZX": [2, 0], "XY": [0, 1]}
            assert start_point, "Start-point must be defined for an AngularArc Segment"
            c_xyz = self._primitives.value_in_object_units(segment_data.arc_center)
            p0_xyz = self._primitives.value_in_object_units(start_point)

            if segment_data.arc_plane:
                # Accept the user input for the plane of rotation - let the modeler fail if invalid
                plane_def = (segment_data.arc_plane, plane_axes[segment_data.arc_plane])
            else:
                # Compare the numeric values of start-point and center-point to determine the orientation plane
                if c_xyz[0] == p0_xyz[0]:
                    plane_def = ("YZ", plane_axes["YZ"])
                elif c_xyz[1] == p0_xyz[1]:
                    plane_def = ("ZX", plane_axes["ZX"])
                elif c_xyz[2] == p0_xyz[2]:
                    plane_def = ("XY", plane_axes["XY"])
                else:
                    raise ("Start point and arc-center do not lie on a common base plane.")

            mod_units = self._primitives.model_units
            seg += [
                "ArcAngle:=",
                segment_data.arc_angle,
                "ArcCenterX:=",
                "{}".format(_dim_arg(segment_data.arc_center[0], mod_units)),
                "ArcCenterY:=",
                "{}".format(_dim_arg(segment_data.arc_center[1], mod_units)),
                "ArcCenterZ:=",
                "{}".format(_dim_arg(segment_data.arc_center[2], mod_units)),
                "ArcPlane:=",
                plane_def[0],
            ]

            # Calculate the extra two points of the angular arc in the alpha-beta plane
            alph_index = plane_def[1][0]
            beta_index = plane_def[1][1]
            c_alph = c_xyz[alph_index]
            c_beta = c_xyz[beta_index]
            p0_alph = p0_xyz[alph_index] - c_alph
            p0_beta = p0_xyz[beta_index] - c_beta

            # rotate to generate the new points
            arc_ang_rad = self._primitives._app.evaluate_expression(segment_data.arc_angle)
            rot_angle = arc_ang_rad * 0.5
            p1_alph = p0_alph * math.cos(rot_angle) + p0_beta * math.sin(rot_angle)
            p1_beta = p0_beta * math.cos(rot_angle) - p0_alph * math.sin(rot_angle)
            p2_alph = p1_alph * math.cos(rot_angle) + p1_beta * math.sin(rot_angle)
            p2_beta = p1_beta * math.cos(rot_angle) - p1_alph * math.sin(rot_angle)

            # Generate the  2 new points in XYZ
            p1 = list(p0_xyz)
            p1[alph_index] = p1_alph + c_alph
            p1[beta_index] = p1_beta + c_alph
            p2 = list(p0_xyz)
            p2[alph_index] = p2_alph + c_alph
            p2[beta_index] = p2_beta + c_beta
            segment_data.extra_points = [p1, p2]

        return seg

    @pyaedt_function_handler()
    def clone(self):
        """Clone a polyline object.

        Returns
        -------
        pyaedt.modeler.Primitives.Polyline
            Polyline object that was created.

        References
        ----------

        >>> oEditor.Copy
        >>> oEditor.Paste

        Examples
        --------
        >>> primitives = self.aedtapp.modeler
        >>> P1 = modeler.create_polyline([[0, 1, 2], [0, 2, 3], [2, 1, 4]])
        >>> P2 = P1.clone()

        """
        vArg1 = ["NAME:Selections", "Selections:=", self.name]
        self._primitives.oeditor.Copy(vArg1)
        self._primitives.oeditor.Paste()
        return self._add_new_polyline()

    @pyaedt_function_handler()
    def _add_new_polyline(self):
        new_objects = self._primitives.find_new_objects()
        assert len(new_objects) == 1
        new_name = new_objects[0]
        new_polyline = Polyline(self._primitives, src_object=self, name=new_name)
        new_polyline._id = None
        self._primitives.objects[new_polyline.id] = new_polyline
        self._primitives.object_id_dict[new_name] = new_polyline.id
        return new_polyline

    @pyaedt_function_handler()
    def remove_vertex(self, position, abstol=1e-9):
        """Remove a vertex from an existing polyline by position.

        You must enter the exact position of the vertex as a list
        of ``[x, y, z]`` coordinates in the object's coordinate system.

        Parameters
        ----------
        position : list
            List of ``[x, y, z]`` coordinates specifying the vertex to remove.
        abstol : float, optional
            Absolute tolerance of the comparison of a specified position to the
            vertex positions. The default is ``1e-9``.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed.

        References
        ----------

        >>> oEditor.DeletePolylinePoint

        Examples
        --------
        Use floating point values for the vertex positions.

        >>> P = modeler.create_polyline([[0, 1, 2], [0, 2, 3], [2, 1, 4]])
        >>> P.remove_vertex([0, 1, 2])

        Use string expressions for the vertex position.

        >>> P = modeler.create_polyline([[0, 1, 2], [0, 2, 3], [2, 1, 4]])
        >>> P.remove_vertex(["0mm", "1mm", "2mm"])

        Use string expressions for the vertex position and include an absolute
        tolerance when searching for the vertex to be removed.

        >>> P = modeler.create_polyline([[0, 1, 2], [0, 2, 3], [2, 1, 4]])
        >>> P.remove_vertex(["0mm", "1mm", "2mm"], abstol=1e-6)
        """
        found_vertex = False
        if self._primitives._app._is_object_oriented_enabled():
            obj = self._primitives.oeditor.GetChildObject(self._m_name).GetChildObject("CreatePolyline:1")
            segments = obj.GetChildNames()
            seg_id = 0
            for seg in segments:
                point = obj.GetChildObject(seg).GetPropValue("Point1")
                p = self._primitives.value_in_object_units([point[1], point[3], point[5]])
                pos_xyz = self._primitives.value_in_object_units(position)
                found_vertex = GeometryOperators.points_distance(p, pos_xyz) <= abstol
                if found_vertex:
                    at_start = True
                    break
                point = obj.GetChildObject(seg).GetPropValue("Point2")
                p = self._primitives.value_in_object_units([point[1], point[3], point[5]])
                found_vertex = GeometryOperators.points_distance(p, pos_xyz) <= abstol
                if found_vertex:
                    at_start = False
                    break
                seg_id += 1
        else:  # pragma: no cover
            pos_xyz = self._primitives.value_in_object_units(position)
            for ind, vertex_pos in enumerate(self.vertex_positions):
                # compare the specified point with the vertex data using an absolute tolerance
                # (default of math.isclose is 1e-9 which should be ok in almost all cases)
                found_vertex = GeometryOperators.points_distance(vertex_pos, pos_xyz) <= abstol
                if found_vertex:
                    if ind == len(self.vertex_positions) - 1:
                        seg_id = ind - 1
                        at_start = True
                    else:
                        seg_id = ind
                        at_start = False
                    break

        assert found_vertex, "Specified vertex {} not found in polyline {}.".format(position, self._m_name)
        self._primitives.oeditor.DeletePolylinePoint(
            [
                "NAME:Delete Point",
                "Selections:=",
                self._m_name + ":CreatePolyline:1",
                "Segment Indices:=",
                [seg_id],
                "At Start:=",
                at_start,
            ]
        )

        return True

    @pyaedt_function_handler()
    def remove_edges(self, edge_id):
        """Remove a vertex from an existing polyline by position.

        You must enter the exact position of the vertex as a list
        of ``[x, y, z]`` coordinates in the object's coordinate system.

        Parameters
        ----------
        edge_id : int or list of int
            One or more edge IDs within the total number of edges within the polyline.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed.

        References
        ----------

        >>> oEditor.DeletePolylinePoint

        Examples
        --------
        >>> P = modeler.create_polyline([[0, 1, 2], [0, 2, 3], [2, 1, 4]])
        >>> P.remove_edges(edge_id=0)
        """
        if isinstance(edge_id, int):
            edge_id = [edge_id]
        try:
            self._primitives.oeditor.DeletePolylinePoint(
                [
                    "NAME:Delete Point",
                    "Selections:=",
                    self.name + ":CreatePolyline:1",
                    "Segment Indices:=",
                    edge_id,
                    "At Start:=",
                    True,
                ]
            )
        except:
            raise ValueError("Invalid edge ID {} is specified on polyline {}.".format(edge_id, self.name))
        return True

    @pyaedt_function_handler()
    def set_crosssection_properties(
        self, type=None, orient=None, width=0, topwidth=0, height=0, num_seg=0, bend_type=None
    ):
        """Set the properties of an existing polyline object.

        Parameters
        ----------
        type : str, optional
            Types of the cross-sections. Options are ``"Line"``, ``"Circle"``, ``"Rectangle"``,
            and ``"Isosceles Trapezoid"``. The default is ``None``.
        orient : str, optional
            Direction of the normal vector to the width of the cross-section.
            Options are ``"X"``, ``"Y"``, ``"Z"``, and ``"Auto"``. The default
            is ``None``, which sets the orientation to ``"Auto"``.
        width : float or str, optional
           Width or diameter of the cross-section for all types. The default is
           ``0``.
        topwidth : float or str
           Top width of the cross-section for the type ``"Isosceles Trapezoid"``
           only. The default is ``0``.
        height : float or str
            Height of the cross-section for the types ``"Rectangle"`` and `"Isosceles
            Trapezoid"`` only. The default is ``0``.
        num_seg : int, optional
            Number of segments in the cross-section surface for the types ``"Circle"``,
            ``"Rectangle"``, and ``"Isosceles Trapezoid"``. The default is ``0``.
            The value must be ``0`` or greater than ``2``.
        bend_type : str, optional
            Type of the bend. The default is ``None``, in which case the bend type
            is set to ``"Corner"``. For the type ``"Circle"``, the bend type should be
            set to ``"Curved"``.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed.

        References
        ----------

        >>> oEditor.ChangeProperty

        Examples
        --------
        >>> P = modeler.create_polyline([[0, 1, 2], [0, 2, 3], [2, 1, 4]])
        >>> P.set_crosssection_properties(type="Circle", width="1mm")

        """
        # Set the default section type to "None"
        section_type = type
        if not section_type:
            section_type = "None"

        # Set the default orientation to "Auto"
        section_orient = orient
        if not section_orient:
            section_orient = "Auto"

        # Set the default bend-type to "Corner"
        section_bend = bend_type
        if not section_bend:
            section_bend = "Corner"

        # Ensure number-of segments is valid
        if num_seg:
            assert num_seg > 2, "Number of segments for a cross-section must be 0 or greater than 2."

        model_units = self._primitives.model_units

        arg1 = ["NAME:AllTabs"]
        arg2 = ["NAME:Geometry3DCmdTab", ["NAME:PropServers", self._m_name + ":CreatePolyline:1"]]
        arg3 = ["NAME:ChangedProps"]
        arg3.append(["NAME:Type", "Value:=", section_type])
        arg3.append(["NAME:Orientation", "Value:=", section_orient])
        arg3.append(["NAME:Bend Type", "Value:=", section_bend])
        arg3.append(["NAME:Width/Diameter", "Value:=", _dim_arg(width, model_units)])
        if section_type == "Rectangle":
            arg3.append(["NAME:Height", "Value:=", _dim_arg(height, model_units)])
        elif section_type == "Circle":
            arg3.append(["NAME:Number of Segments", "Value:=", num_seg])
        elif section_type == "Isosceles Trapezoid":
            arg3.append(["NAME:Top Width", "Value:=", _dim_arg(topwidth, model_units)])
            arg3.append(["NAME:Height", "Value:=", _dim_arg(height, model_units)])
        arg2.append(arg3)
        arg1.append(arg2)
        self._primitives.oeditor.ChangeProperty(arg1)
        self._update()
        return True

    @pyaedt_function_handler()
    def insert_segment(self, position_list, segment=None, segment_number=0):
        """Add a segment to an existing polyline.

        Parameters
        ----------
        position_list : list
            List of positions of the points that define the segment to insert.
            Either the starting point or ending point of the segment list must
            match one of the vertices of the existing polyline.
        segment : str or :class:`pyaedt.modeler.Primitives.PolylineSegment`
            Definition of the segment to insert. For the types ``"Line"`` and ``"Arc"``,
            use their string values ``"Line"`` and ``"Arc"``. For the types ``"AngularArc"``
            and ``"Spline"``, use the :class:`pyaedt.modeler.Primitives.PolylineSegment`
            object to define the segment precisely.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed.

        References
        ----------

        >>> oEditor.InsertPolylineSegment

        """

        # Check for a valid number of points
        num_points = len(position_list)

        # define the segment type from the number of points given
        if not segment:
            if num_points == 2:
                segment = PolylineSegment("Line")
            elif num_points == 3:
                segment = PolylineSegment("Arc")
            else:
                segment = PolylineSegment("Spline", num_points=num_points)
        else:
            if isinstance(segment, str):
                segment = PolylineSegment(segment)
            num_points = segment.num_points

        # Check whether start-point of the segment is in the existing vertices
        start_point = self._primitives.value_in_object_units(position_list[0])

        # End point does not exist e.g. for an AngularArc
        try:
            end_point = self._primitives.value_in_object_units(position_list[num_points - 1])
        except:
            end_point = []

        segment_id = 1
        segment_index = 0
        num_vertices = len(self.vertices)
        for vertex in self.vertices:
            if vertex.position == end_point:
                if vertex.id == self.vertices[0].id:
                    if segment_id > 0:
                        segment_id -= 1
                at_start = True
                break
            # If start_point=[0, 0, 0] (a list of integers provided by the user), it won't be equal to vertex.position
            # that returns a list of float: [0., 0., 0.]. Thus we cast start_point as a list of floats.
            elif vertex.position == [float(x) for x in start_point]:
                at_start = False
                if segment_index > 0:
                    segment_index -= 1
                break
            segment_index += 1
        id_v = 0

        if isinstance(self._segment_types, list):
            s_types = [i for i in self._segment_types]
        else:
            s_types = [self._segment_types]
        for el in s_types:
            if isinstance(s_types, PolylineSegment):
                id_v += el.num_seg - 1
                if id_v > segment_index:
                    id_v -= el.num_seg - 1
                    break
        segment_index -= id_v

        assert segment_index < num_vertices, "Vertex for the insert is not found."
        type = segment.type

        varg1 = ["NAME:Insert Polyline Segment="]
        varg1.append("Selections:=")
        varg1.append(self._m_name + ":CreatePolyline:1")
        varg1.append("Segment Indices:=")
        varg1.append([segment_index])
        varg1.append("At Start:=")
        varg1.append(at_start)
        varg1.append("SegmentType:=")
        varg1.append(type)

        # Points and segment data
        varg2 = ["NAME:PolylinePoints"]

        if segment.type == "Line" or segment.type == "Spline" or segment.type == "Arc":
            for pt in position_list[0:num_points]:
                varg2.append(self._pl_point(pt))
            varg1.append(varg2)
        elif segment.type == "AngularArc":
            seg_str = self._segment_array(segment, start_point=start_point)
            varg2.append(self._pl_point(start_point))
            varg2.append(self._pl_point(segment.extra_points[0]))
            varg2.append(self._pl_point(segment.extra_points[1]))
            varg1.append(varg2)
            varg1 += seg_str[9:]
        self._primitives.oeditor.InsertPolylineSegment(varg1)

        if segment.type == "Spline":
            varg1 = ["NAME:AllTabs"]
            varg2 = ["NAME:Geometry3DPolylineTab"]

            varg3 = ["NAME:PropServers"]
            varg3.append(self._m_name + ":CreatePolyline:1" + ":Segment" + str(segment_id))
            varg2.append(varg3)

            varg4 = ["NAME:ChangedProps"]
            varg5 = ["NAME:Number of Segments"]
            varg5.append("Value:=")
            varg5.append(str(segment_number))

            varg4.append(varg5)
            varg2.append(varg4)
            varg1.append(varg2)

            self._primitives.oeditor.ChangeProperty(varg1)

        return True


class Primitives(object):
    """Provides common functionalities for primitives.

    Parameters
    ----------
    application : :class:`pyaedt.modeler.Model3D.Modeler3D`, :class:`pyaedt.modeler.Model2D.Modeler2D`
        Pointer to the parent object.

    Examples
    --------
    Basic usage demonstrated with an HFSS design:

    >>> from pyaedt import Hfss
    >>> aedtapp = Hfss()
    >>> prim = aedtapp.modeler
    """

    def __init__(self):
        self.refresh()

    @property
    def _modeler(self):
        return self._app.modeler

    @property
    def solid_objects(self):
        """List of all solid objects."""
        self._refresh_solids()
        return [self[name] for name in self.solid_names if self[name]]

    @property
    def sheet_objects(self):
        """List of all sheet objects."""
        self._refresh_sheets()
        return [self[name] for name in self.sheet_names if self[name]]

    @property
    def line_objects(self):
        """List of all line objects."""
        self._refresh_lines()
        return [self[name] for name in self.line_names if self[name]]

    @property
    def points(self):
        """List of points."""
        return self._points

    @property
    def points_by_name(self):
        """Dictionary containing all points where the keys are the name of the points."""
        return self._point_names

    @property
    def unclassified_objects(self):
        """List of all unclassified objects."""
        self._refresh_unclassified()
        return [self[name] for name in self._unclassified]

    @property
    def object_list(self):
        """List of all objects."""
        self._refresh_object_types()
        return [self[name] for name in self._all_object_names]

    @property
    def solid_names(self):
        """List of the names of all solid objects."""
        self._refresh_solids()
        return self._solids

    @property
    def sheet_names(self):
        """List of the names of all sheet objects."""
        self._refresh_sheets()
        return self._sheets

    @property
    def line_names(self):
        """List of the names of all line objects."""
        self._refresh_lines()
        return self._lines

    @property
    def unclassified_names(self):
        """List of the names of all unclassified objects."""
        self._refresh_unclassified()
        return self._unclassified

    @property
    def object_names(self):
        """List of the names of all objects."""
        self._refresh_object_types()
        return [i for i in self._all_object_names if i not in self._unclassified]

    @property
    def user_defined_component_names(self):
        """List of the names of all 3D component objects.

        References
        ----------

        >>> oEditor.Get3DComponentDefinitionNames
        >>> oEditor.Get3DComponentInstanceNames
        """
        obs3d = []
        try:
            comps3d = self.oeditor.Get3DComponentDefinitionNames()
            for comp3d in comps3d:
                obs3d += list(self.oeditor.Get3DComponentInstanceNames(comp3d))
            udm = self._get_user_defined_component_names()
            obs3d = list(set(udm + obs3d))
            new_obs3d = copy.deepcopy(obs3d)
            if self.user_defined_components:
                existing_components = list(self.user_defined_components.keys())
                new_obs3d = [i for i in obs3d if i]
                for _, value in enumerate(existing_components):
                    if value not in new_obs3d:
                        new_obs3d.append(value)

        except Exception as e:
            new_obs3d = []
        return new_obs3d

    @property
    def _oproject(self):
        """Project."""
        return self._app.oproject

    @property
    def _odesign(self):
        """Design."""
        return self._app._odesign

    @property
    def _materials(self):
        """Material Manager that is used to manage materials in the project.

        Returns
        -------
        :class:`pyaedt.modules.MaterialLib.Materials`
            Material Manager that is used to manage materials in the project.
        """
        return self._app.materials

    @property
    def defaultmaterial(self):
        """Default material."""
        return default_materials[self._app._design_type]

    @property
    def logger(self):
        """Logger."""
        return self._app.logger

    @property
    def version(self):
        """Version."""
        return self._app._aedt_version

    @property
    def modeler(self):
        """Modeler."""
        return self._modeler

    @property
    def model_units(self):
        """Model units."""
        return self.modeler.model_units

    @property
    def model_objects(self):
        """List of the names of all model objects."""
        return self._get_model_objects(model=True)

    @property
    def non_model_objects(self):
        """List of names of all non-model objects."""
        return self._get_model_objects(model=False)

    @property
    def model_consistency_report(self):
        """Summary of detected inconsistencies between the AEDT modeler and PyAEDT structures.

        Returns
        -------
        dict

        """
        obj_names = self.object_names
        missing = []
        for name in obj_names:
            if name not in self.object_id_dict:
                missing.append(name)
        non_existent = []
        for name in self.object_id_dict:
            if name not in obj_names and name not in self.unclassified_names:
                non_existent.append(name)
        report = {"Missing Objects": missing, "Non-Existent Objects": non_existent}
        return report

    @pyaedt_function_handler()
    def _change_component_property(self, vPropChange, names_list):
        names = self._app.modeler.convert_to_selections(names_list, True)
        vChangedProps = ["NAME:ChangedProps", vPropChange]
        vPropServers = ["NAME:PropServers"]
        for el in names:
            vPropServers.append(el)
        vGeo3d = ["NAME:General", vPropServers, vChangedProps]
        vOut = ["NAME:AllTabs", vGeo3d]
        _retry_ntimes(10, self.oeditor.ChangeProperty, vOut)
        return True

    @pyaedt_function_handler()
    def _change_geometry_property(self, vPropChange, names_list):
        names = self._app.modeler.convert_to_selections(names_list, True)
        vChangedProps = ["NAME:ChangedProps", vPropChange]
        vPropServers = ["NAME:PropServers"]
        for el in names:
            vPropServers.append(el)
        vGeo3d = ["NAME:Geometry3DAttributeTab", vPropServers, vChangedProps]
        vOut = ["NAME:AllTabs", vGeo3d]
        _retry_ntimes(10, self.oeditor.ChangeProperty, vOut)
        if "NAME:Name" in vPropChange:
            self.cleanup_objects()
        return True

    @pyaedt_function_handler()
    def _change_point_property(self, vPropChange, names_list):
        names = self._app.modeler.convert_to_selections(names_list, True)
        vChangedProps = ["NAME:ChangedProps", vPropChange]
        vPropServers = ["NAME:PropServers"]
        for el in names:
            vPropServers.append(el)
        vGeo3d = ["NAME:Geometry3DPointTab", vPropServers, vChangedProps]
        vOut = ["NAME:AllTabs", vGeo3d]
        _retry_ntimes(10, self.oeditor.ChangeProperty, vOut)
        if "NAME:Name" in vPropChange:
            self.cleanup_objects()
        return True

    @pyaedt_function_handler()
    def update_object(self, obj):
        """Update any :class:`pyaedt.modeler.Object3d.Object3d` derivatives
        that have potentially been modified by a modeler operation.

        Parameters
        ----------
        obj : int, str, or :class:`pyaedt.modeler.Object3d.Object3d`
            Object to be updated after a modeler operation.

        Returns
        -------
        :class:`pyaedt.modeler.Object3d.Object3d`
           Updated 3D object.

        """
        o = self._resolve_object(obj)
        o._update()
        return o

    @pyaedt_function_handler()
    def value_in_object_units(self, value):
        """Convert one or more strings for numerical lengths to floating point values.

        Parameters
        ----------
        value : string or list of strings
            One or more strings for numerical lengths. For example, ``"10mm"``
            or ``["10mm", "12mm", "14mm"]``. When a a list is given, the entire
            list is converted.

        Returns
        -------
        float or list of floats
            Defined in object units :attr:`pyaedt.modeler.Primitives.Polyline.object_units`

        """
        # Convert to a list if a scalar is presented

        scalar = False
        if not isinstance(value, list):
            value = [value]
            scalar = True

        numeric_list = []
        for element in value:
            if is_number(element):
                num_val = element
            elif isinstance(element, str):
                # element is an existing variable
                si_value = self._app.evaluate_expression(element)
                v = Variable("{}meter".format(si_value))
                v.rescale_to(self.model_units)
                num_val = v.numeric_value
            else:
                raise ("Inputs to value_in_object_units must be strings or numbers.")

            numeric_list.append(num_val)

        if scalar:
            return numeric_list[0]
        else:
            return numeric_list

    @pyaedt_function_handler()
    def does_object_exists(self, object):
        """ "Check to see if an object exists.

        Parameters
        ----------
        object : str, int
            Object name or object ID.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed

        """
        if isinstance(object, int):
            if object in self.objects:
                return True
            else:
                return False
        else:
            for el in self.objects:
                if self.objects[el].name == object:
                    return True

        return False

    @pyaedt_function_handler()
    def create_region(self, pad_percent=300):
        """Create an air region.

        Parameters
        ----------
        pad_percent : float or list of floats, optional
            If a float, use padding in percent for all dimensions. The default is ``300``.
            If a list of floats, interpret as adding for ``["+X", "+Y", "+Z", "-X", "-Y", "-Z"]``.

        Returns
        -------
        :class:`pyaedt.modeler.Object3d.Object3d`
            Region object.

        References
        ----------

        >>> oEditor.CreateRegion
        """
        if "Region" in self.object_names:
            return None
        if is_number(pad_percent):
            pad_percent = [pad_percent] * 6

        arg = ["NAME:RegionParameters"]
        p = ["+X", "+Y", "+Z", "-X", "-Y", "-Z"]
        i = 0
        for pval in p:
            pvalstr = str(pval) + "PaddingType:="
            qvalstr = str(pval) + "Padding:="
            arg.append(pvalstr)
            arg.append("Percentage Offset")
            arg.append(qvalstr)
            arg.append(str(pad_percent[i]))
            i += 1
        arg2 = [
            "NAME:Attributes",
            "Name:=",
            "Region",
            "Flags:=",
            "Wireframe#",
            "Color:=",
            "(143 175 143)",
            "Transparency:=",
            0.75,
            "PartCoordinateSystem:=",
            "Global",
            "UDMId:=",
            "",
            "MaterialValue:=",
            '"air"',
            "SurfaceMaterialValue:=",
            '""',
            "SolveInside:=",
            True,
            "IsMaterialEditable:=",
            True,
            "UseMaterialAppearance:=",
            False,
            "IsLightweight:=",
            False,
        ]
        self.oeditor.CreateRegion(arg, arg2)
        return self._create_object("Region")

    @pyaedt_function_handler()
    def create_object_from_edge(self, edge):
        """Create a line object from an edge ID or from an
        :class:`pyaedt.modeler.Object3d.EdgePrimitive` object.

        Parameters
        ----------
        edge : int or :class:`pyaedt.modeler.Object3d.EdgePrimitive`
            Edge ID or :class:`pyaedt.modeler.Object3d.EdgePrimitive` object.

        Returns
        -------
        :class:`pyaedt.modeler.Object3d.Object3d`
            3D object.

        References
        ----------

        >>> oEditor.CreateObjectFromEdges
        """
        if isinstance(edge, EdgePrimitive):
            edge_id = edge.id
        else:
            edge_id = edge

        obj = self._find_object_from_edge_id(edge_id)

        if obj is not None:

            varg1 = ["NAME:Selections"]
            varg1.append("Selections:="), varg1.append(obj)
            varg1.append("NewPartsModelFlag:="), varg1.append("Model")

            varg2 = ["NAME:BodyFromEdgeToParameters"]
            varg2.append("Edges:="), varg2.append([edge_id])

            new_object_name = self.oeditor.CreateObjectFromEdges(varg1, ["NAME:Parameters", varg2])[0]
            return self._create_object(new_object_name)

    @pyaedt_function_handler()
    def create_object_from_face(self, face):
        """Create an object from a face.

        Parameters
        ----------
        face : int or :class:`pyaedt.modeler.Object3d.FacePrimitive`
            Face ID or :class:`pyaedt.modeler.Object3d.FacePrimitive` object.

        Returns
        -------
        :class:`pyaedt.modeler.Object3d.Object3d`
            3D object.

        References
        ----------

        >>> oEditor.CreateObjectFromFaces
        """
        face_id = face
        if isinstance(face, FacePrimitive):
            face_id = face.id
        obj = self._find_object_from_face_id(face_id)
        if obj is not None:

            varg1 = ["NAME:Selections"]
            varg1.append("Selections:="), varg1.append(obj)
            varg1.append("NewPartsModelFlag:="), varg1.append("Model")

            varg2 = ["NAME:BodyFromFaceToParameters"]
            varg2.append("FacesToDetach:="), varg2.append([face_id])
            new_object_name = self.oeditor.CreateObjectFromFaces(varg1, ["NAME:Parameters", varg2])[0]
            return self._create_object(new_object_name)

    @pyaedt_function_handler()
    def create_polyline(
        self,
        position_list,
        segment_type=None,
        cover_surface=False,
        close_surface=False,
        name=None,
        matname=None,
        xsection_type=None,
        xsection_orient=None,
        xsection_width=1,
        xsection_topwidth=1,
        xsection_height=1,
        xsection_num_seg=0,
        xsection_bend_type=None,
        non_model=False,
    ):
        """Draw a polyline object in the 3D modeler.

        This method retrieves the
        :class:`pyaedt.modeler.Primitives.Polyline` object, which has
        additional methods for manipulating the polyline. For example,
        you can use
        :func:`pyaedt.modeler.Primitives.Polyline.insert_segment` to
        insert a segment or
        :attr:`pyaedt.modeler.Primitives.Polyline.id` to retrieve the
        ID of the polyline object.

        Parameters
        ----------
        position_list : list
            Array of positions of each point of the polyline.  A
            position is a list of 2D or 3D coordinates. Position
            coordinate values can be numbers or valid AEDT string
            expressions. For example, ``[0, 1, 2]``, ``["0mm", "5mm",
            "1mm"]``, or ``["x1", "y1", "z1"]``.
        segment_type : str or PolylineSegment or list, optional
            The default behavior is to connect all points as
            ``"Line"`` segments. The default is ``None``. For a
            string, ``"Line"`` or ``"Arc"`` is valid. For a
            ``"PolylineSegment"``, for ``"Line",`` ``"Arc"``,
            ``"Spline"``, or ``"AngularArc"``, a list of segment types
            (str or
            :class:`pyaedt.modeler.Primitives.PolylineSegment`) is
            valid for a compound polyline.
        cover_surface : bool, optional
            The default is ``False``.
        close_surface : bool, optional
            The default is ``False``, which automatically joins the
            starting and ending points.
        name : str, optional
            Name of the polyline. The default is ``None``.
        matname : str, optional
            Name of the material. The default is ``None``, in which case the
            default material is assigned.
        xsection_type : str, optional
            Type of the cross-section. Options are ``"Line"``, ``"Circle"``,
            ``"Rectangle"``, and ``"Isosceles Trapezoid"``. The default is ``None``.
        xsection_orient : str, optional
            Direction of the normal vector to the width of the cross-section.
            Options are ``"X"``, ``"Y"``, ``"Z"``, and ``"Auto"``. The default is
            ``None``, which sets the direction to ``"Auto"``.
        xsection_width : float or str, optional
            Width or diameter of the cross-section for all  types. The
            default is ``1``.
        xsection_topwidth : float or str, optional
            Top width of the cross-section for type ``"Isosceles Trapezoid"`` only.
            The default is ``1``.
        xsection_height : float or str
            Height of the cross-section for type ``"Rectangle"`` or ``"Isosceles
            Trapezoid"`` only. The default is ``1``.
        xsection_num_seg : int, optional
            Number of segments in the cross-section surface for type ``"Circle"``,
            ``"Rectangle"``, or ``"Isosceles Trapezoid"``. The default is ``0``. The
            value must be ``0`` or greater than ``2``.
        xsection_bend_type : str, optional
            Type of the bend for the cross-section. The default is
            ``None``, in which case the bend type is set to
            ``"Corner"``. For the type ``"Circle"``, the bend type
            should be set to ``"Curved"``.
        non_model : bool, optional
            Either if the polyline will be created as model or unmodel object.

        Returns
        -------
        pyaedt.modeler.Primitives.Polyline
           Polyline object.

        References
        ----------

        >>> oEditor.CreatePolyline

        Examples
        --------
        Set up the desktop environment.

        >>> from pyaedt.desktop import Desktop
        >>> from pyaedt.maxwell import Maxwell3d
        >>> from pyaedt.modeler.Primitives import PolylineSegment
        >>> desktop=Desktop(specified_version="2021.2", new_desktop_session=False)
        >>> aedtapp = Maxwell3D()
        >>> aedtapp.modeler.model_units = "mm"
        >>> modeler = aedtapp.modeler

        Define some test data points.

        >>> test_points = [["0mm", "0mm", "0mm"], ["100mm", "20mm", "0mm"],
        ...                ["71mm", "71mm", "0mm"], ["0mm", "100mm", "0mm"]]

        The default behavior assumes that all points are to be
        connected by line segments.  Optionally specify the name.

        >>> P1 = modeler.create_polyline(test_points, name="PL_line_segments")

        Specify that the first segment is a line and the last three
        points define a three-point arc.

        >>> P2 = modeler.create_polyline(test_points, segment_type=["Line", "Arc"], name="PL_line_plus_arc")

        Redraw the 3-point arc alone from the last three points and
        additionally specify five segments using ``PolylineSegment``.

        >>> P3 = modeler.create_polyline(test_points[1:],
        ...                               segment_type=PolylineSegment(type="Arc", num_seg=7),
        ...                               name="PL_segmented_arc")

        Specify that the four points form a spline and add a circular
        cross-section with a diameter of 1 mm.

        >>> P4 = modeler.create_polyline(test_points, segment_type="Spline", name="PL_spline",
        ...                               xsection_type="Circle", xsection_width="1mm")

        Use the `PolylineSegment` object to specify more detail about
        the individual segments.  Create a center point arc starting
        from the position ``test_points[1]``, rotating about the
        center point position ``test_points[0]`` in the XY plane.

        >>> start_point = test_points[1]
        >>> center_point = test_points[0]
        >>> segment_def = PolylineSegment(type="AngularArc", arc_center=center_point, arc_angle="90deg", arc_plane="XY")
        >>> modeler.create_polyline(start_point, segment_type=segment_def, name="PL_center_point_arc")

        Create a spline using a list of variables for the coordinates of the points.

        >>> x0, y0, z0 = "0", "0", "1"
        >>> x1, y1, z1 = "1", "3", "1"
        >>> x2, y2, z2 = "2", "2", "1"
        >>> P5 = modeler.create_polyline(position_list = [[x0, y0, z0], [x1, y1, z1], [x2, y2, z2]],
        ...                                 segment_type="Spline", name="polyline_with_variables")

        """
        new_polyline = Polyline(
            primitives=self,
            position_list=position_list,
            segment_type=segment_type,
            cover_surface=cover_surface,
            close_surface=close_surface,
            name=name,
            matname=matname,
            xsection_type=xsection_type,
            xsection_orient=xsection_orient,
            xsection_width=xsection_width,
            xsection_topwidth=xsection_topwidth,
            xsection_height=xsection_height,
            xsection_num_seg=xsection_num_seg,
            xsection_bend_type=xsection_bend_type,
            non_model=non_model,
        )
        return new_polyline

    @pyaedt_function_handler()
    def create_spiral_on_face(self, face, poly_width, filling_factor=1.5):
        """Create a Spiral Polyline inside a face.

        Parameters
        ----------
        face : int or str or :class:`pyaedt.modeler.Object3d.FacePrimitive`
        poly_width : float
        filling_factor : float

        Returns
        -------
        :class:`pyaedt.modeler.Object3d.Polyline`
        """
        # fmt: off
        if isinstance(face, FacePrimitive):
            face_id = face.id
        elif isinstance(face, int):
            face_id = face
        else:
            face_id = self.get_object_faces(face)[0]

        vertices = self.get_face_vertices(face_id)
        vertex_coordinates = []
        for v in vertices:
            vertex_coordinates.append(self.get_vertex_position(v))

        centroid = self.get_face_center(face_id)

        segments_lengths = []
        for vc in vertex_coordinates:
            segments_lengths.append(GeometryOperators.points_distance(vc, centroid))

        n = math.floor(min(segments_lengths) / (poly_width * filling_factor))

        if n % 2 == 0:
            n_points = int(n / 2 - 1)
        else:
            n_points = int((n - 1) / 2)

        if n_points < 1:
            raise Exception

        inner_points = []
        for vc in vertex_coordinates:
            temp = [[] for i in range(n_points)]
            for i in range(3):  # loop for x, y, z
                delta = (centroid[i] - vc[i]) / (n_points + 1)
                for j in range(1, n_points + 1):
                    temp[j - 1].append(vc[i] + delta * j)
            inner_points.append(temp)

        poly_points_list = []
        for p in range(n_points):
            for v in inner_points:
                poly_points_list.append(v[p])

        del poly_points_list[-1]

        # fmt: on
        return self.create_polyline(poly_points_list, xsection_type="Line", xsection_width=poly_width)

    @pyaedt_function_handler()
    def get_existing_polyline(self, object):
        """Retrieve a polyline object to manipulate it.

        Parameters
        ----------
        src_object : :class:`pyaedt.modeler.Object3d.Object3d`
            An existing polyline object in the 3D Modeler.

        Returns
        -------
        Polyline
        """
        return Polyline(self, src_object=object)

    @pyaedt_function_handler()
    def create_udp(self, udp_dll_name, udp_parameters_list, upd_library="syslib", name=None, udp_type="Solid"):
        """Create a user-defined primitive (UDP).

        Parameters
        ----------
        udp_dll_name : str
            Name of the UPD DLL.
        udp_parameters_list :
            List of the UDP parameters.
        upd_library : str, optional
            Name of the UDP library. The default is ``"syslib"``.
        name : str, optional
            Name of the component. The default is ``None``.
        udp_type : str, optional
            Type of the UDP. The default is ``"Solid"``.

        Returns
        -------
        :class:`pyaedt.modeler.Object3d.Object3d`
            UDP object created.

        References
        ----------

        >>> oEditor.CreateUserDefinedPart

        Examples
        --------
        >>> my_udp = self.aedtapp.modeler.create_udp(udp_dll_name="RMxprt/ClawPoleCore",
        ...                                          udp_parameters_list=my_udpPairs,
        ...                                          upd_library="syslib",
        ...                                          udp_type="Solid")
        <class 'pyaedt.modeler.Object3d.Object3d'>

        """
        if ".dll" not in udp_dll_name:
            vArg1 = [
                "NAME:UserDefinedPrimitiveParameters",
                "DllName:=",
                udp_dll_name + ".dll",
                "Library:=",
                upd_library,
            ]
        else:
            vArg1 = ["NAME:UserDefinedPrimitiveParameters", "DllName:=", udp_dll_name, "Library:=", upd_library]

        vArgParamVector = ["NAME:ParamVector"]

        for pair in udp_parameters_list:
            if isinstance(pair, list):
                vArgParamVector.append(["NAME:Pair", "Name:=", pair[0], "Value:=", pair[1]])

            else:
                vArgParamVector.append(["NAME:Pair", "Name:=", pair.Name, "Value:=", pair.Value])

        vArg1.append(vArgParamVector)
        if name:
            obj_name = name
        else:
            obj_name, ext = os.path.splitext(os.path.basename(udp_dll_name))
        vArg2 = self._default_object_attributes(name=obj_name)
        obj_name = self.oeditor.CreateUserDefinedPart(vArg1, vArg2)
        return self._create_object(obj_name)

    @pyaedt_function_handler()
    def update_udp(self, object_name, operation_name, udp_parameters_list):
        """Update an existing geometrical object that was originally created using a user-defined primitive (UDP).

        Parameters
        ----------
        object_name : str
            Name of the object to update.
        operation_name : str
            Name of the operation used to create the object.
        udp_parameters_list : list
            List of the UDP parameters to update and their value.

        Returns
        -------
        bool
            ``True`` when successful.

        References
        ----------

        >>> oEditor.CreateUserDefinedPart

        Examples
        --------
        >>> self.aedtapp.modeler.update_udp(object_name="ClawPoleCore",
        ...                                 operation_name="CreateUserDefinedPart",
        ...                                 udp_parameters_list=[["Length","110mm"], ["DiaGap","125mm"]])
        True

        """

        vArg1 = ["NAME:AllTabs"]

        prop_servers = ["NAME:PropServers"]
        prop_servers.append("{0}:{1}:1".format(object_name, operation_name))

        cmd_tab = ["NAME:Geometry3DCmdTab"]
        cmd_tab.append(prop_servers)

        changed_props = ["NAME:ChangedProps"]

        for pair in udp_parameters_list:
            if isinstance(pair, list):
                changed_props.append(["NAME:{0}".format(pair[0]), "Value:=", pair[1]])
            else:
                changed_props.append(["NAME:", pair.Name, "Value:=", pair.Value])

        cmd_tab.append(changed_props)
        vArg1.append(cmd_tab)
        self.oeditor.ChangeProperty(vArg1)
        return True

    @pyaedt_function_handler()
    def delete(self, objects=None):
        """Delete objects or groups.

        Parameters
        ----------
        objects : list, optional
            List of objects or group names. The default is ``None``,
            in which case all objects are deleted.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed

        References
        ----------

        >>> oEditor.Delete

        """
        if objects is None:
            objects = self.object_names
        objects = self._modeler.convert_to_selections(objects, return_list=True)
        for el in objects:
            if el not in self.object_names and not list(self.oeditor.GetObjectsInGroup(el)):
                objects.remove(el)
        if not objects:
            self.logger.warning("No objects to delete")
            return False
        slice = min(100, len(objects))
        num_objects = len(objects)
        remaining = num_objects
        while remaining > 0:
            objs = objects[:slice]
            objects_str = self._modeler.convert_to_selections(objs, return_list=False)
            arg = ["NAME:Selections", "Selections:=", objects_str]
            try:
                self.oeditor.Delete(arg)
            except:
                self.logger.warning("Failed to delete {}.".format(objects_str))
            remaining -= slice
            if remaining > 0:
                objects = objects[slice:]

        self._refresh_object_types()

        if len(objects) > 0:
            self.cleanup_objects()
            self.logger.info("Deleted {} Objects: {}.".format(num_objects, objects_str))
        return True

    @pyaedt_function_handler()
    def delete_objects_containing(self, contained_string, case_sensitive=True):
        """Delete all objects with a given prefix.

        Parameters
        ----------
        contained_string : str
            Prefix in the names of the objects to delete.
        case_sensitive : bool, optional
            Whether the prefix is case-senstive. The default is ``True``.

        Returns
        -------
        bool
            ``True`` when successful, ``False`` when failed

        References
        ----------

        >>> oEditor.Delete

        """
        objnames = self.object_id_dict
        num_del = 0
        for el in objnames:
            if case_sensitive:
                if contained_string in el:
                    self.delete(el)
                    num_del += 1
            else:
                if contained_string.lower() in el.lower():
                    self.delete(el)
                    num_del += 1
        self.logger.info("Deleted %s objects", num_del)
        return True

    @pyaedt_function_handler()
    def get_model_bounding_box(self):
        """Retrieve the model's bounding box.

        Returns
        -------
        list
            List of 6 float values ``[min_x, min_y, min_z, max_x, max_y, max_z]``
            for the bounding box.

        References
        ----------

        >>> oEditor.GetModelBoundingBox
        """
        return self._app.modeler.get_model_bounding_box()

    @pyaedt_function_handler()
    def get_obj_id(self, objname):
        """Return the object ID from an object name.

        Parameters
        ----------
        objname : str
            Name of the object.

        Returns
        -------
        int
            Object ID.

        """
        if objname in self.object_id_dict:
            return self.object_id_dict[objname]
        return None

    @pyaedt_function_handler()
    def get_object_from_name(self, objname):
        """Return the object from an object name.

        Parameters
        ----------
        objname : str
            Name of the object.

        Returns
        -------
        :class:`pyaedt.modeler.Object3d.Object3d`
            3D object returned.

        """
        if objname in self.object_id_dict:
            id = self.get_obj_id(objname)
            return self.objects[id]

    @pyaedt_function_handler()
    def get_objects_w_string(self, stringname, case_sensitive=True):
        """Retrieve all objects with a given string in their names.

        Parameters
        ----------
        stringname : str
            String to search object names for.
        case_sensitive : bool, optional
            Whether the string is case-sensitive. The default is ``True``.

        Returns
        -------
        list
            List of object names with the given string.

        """
        list_objs = []
        for el in self.objects:
            if case_sensitive:
                if stringname in self.objects[el].name:
                    list_objs.append(self.objects[el].name)
            else:
                if stringname.lower() in self.objects[el].name.lower():
                    list_objs.append(self.objects[el].name)

        return list_objs

    @pyaedt_function_handler()
    def refresh(self):
        """Refresh this object."""
        self._solids = []
        self._sheets = []
        self._lines = []
        self._points = []
        self._point_names = {}
        self._unclassified = []
        self._all_object_names = []
        self.objects = {}
        self.user_defined_components = {}
        self.object_id_dict = {}
        self._currentId = 0
        self.refresh_all_ids()
        # self._refresh_all_ids_from_aedt_file()

    @pyaedt_function_handler()
    def cleanup_objects(self):
        """Clean up objects that no longer exist in the modeler because
        they were removed by previous operations.

        This method also updates object IDs that may have changed via
        a modeler operation such as :func:`pyaedt.modeler.Model3D.Modeler3D.unite`
        or :func:`pyaedt.modeler.Model2D.Modeler2D.unite`.

        Returns
        -------
        dict
           Dictionary of updated object IDs.

        """
        new_object_dict = {}
        new_object_id_dict = {}
        all_objects = self.object_names
        all_unclassified = self.unclassified_objects
        for old_id, obj in self.objects.items():
            if obj.name in all_objects or obj.name in all_unclassified:
                updated_id = obj.id  # By calling the object property we get the new id
                new_object_id_dict[obj.name] = updated_id
                new_object_dict[updated_id] = obj

        self.objects = new_object_dict
        self.object_id_dict = new_object_id_dict

    @pyaedt_function_handler()
    def remove_point(self, name):
        """Remove a point.

        Parameters
        ----------
        name : str
            Name of the point to be removed.

        Returns
        -------
        """
        self._points.remove(self.points_by_name[name])
        del self.points_by_name[name]

    @pyaedt_function_handler()
    def find_new_objects(self):
        """Find any new objects in the modeler that were created
        by previous operations.

        Returns
        -------
        dict
            Dictionary of new objects.

        """
        new_objects = []
        for obj_name in self.object_names:
            if obj_name not in self.object_id_dict:
                new_objects.append(obj_name)
        return new_objects

    @pyaedt_function_handler()
    def add_new_objects(self):
        """Add objects that have been created in the modeler by
        previous operations.

        Returns
        -------
        list
            List of added objects.

        """
        added_objects = []
        for obj_name in self.object_names:
            if obj_name not in self.object_id_dict:
                self._create_object(obj_name)
                added_objects.append(obj_name)
        for obj_name in self.unclassified_names:
            if obj_name not in self.object_id_dict:
                self._create_object(obj_name)
                added_objects.append(obj_name)
        return added_objects

    @pyaedt_function_handler()
    def add_new_user_defined_component(self):
        """Add 3D components and user-defined models that have been created in the modeler by
        previous operations.

        Returns
        -------
        list
            List of added components.

        """
        added_component = []
        for comp_name in self.user_defined_component_names:
            if comp_name not in self.user_defined_components:
                self._create_user_defined_component(comp_name)
            added_component.append(comp_name)
        return added_component

    # TODO Eliminate this - check about import_3d_cad
    # Should no longer be a problem
    @pyaedt_function_handler()
    def refresh_all_ids(self):
        """Refresh all IDs."""

        self.add_new_objects()
        self.add_new_user_defined_component()
        self.cleanup_objects()

        return len(self.objects)

    @pyaedt_function_handler()
    def get_objects_by_material(self, materialname):
        """Retrieve a list of the IDs for objects of a specified material.

        Parameters
        ----------
        materialname : str
            Name of the material.

        Returns
        -------
        list
            List of IDs for objects of the specified material.

        References
        ----------

        >>> oEditor.GetObjectsByMaterial

        """
        obj_lst = []
        for el in self.objects:
            if (
                self.objects[el].material_name == materialname
                or self.objects[el].material_name == '"' + materialname + '"'
            ):
                obj_lst.append(el)
        return obj_lst

    @pyaedt_function_handler()
    def find_closest_edges(self, start_obj, end_obj, port_direction=0):
        """Retrieve the two closest edges that are not perpendicular for two objects.

        Parameters
        ----------
        start_obj : str
            Name of the starting object.
        end_obj : str
            Name of the ending object.
        port_direction : str, optional
            Direction of the port to which to give edges precedence when more than two couples
            are at the same distance. For example, for a coax or microstrip, precedence is given
            to the edges that are on the given axis direction, such as ``"XNeg"``. Options are
            ``"XNeg"``, ``"XPos"``, ``"YNeg"``, ``"YPos`"``, ``"ZNeg"``, and ``"ZPos"``.
            The default is ``0``.

        Returns
        -------
        list
            List with two edges if present.

        """
        start_obj = self._resolve_object(start_obj)
        end_obj = self._resolve_object(end_obj)
        edge_start_list = None
        edge_stop_list = None
        if port_direction == 0:
            if start_obj.bottom_face_x:
                edge_start_list = start_obj.bottom_face_x.edges
            if end_obj.bottom_face_x:
                edge_stop_list = end_obj.bottom_face_x.edges
        elif port_direction == 3:
            if start_obj.top_face_x:
                edge_start_list = start_obj.top_face_x.edges
            if end_obj.top_face_x:
                edge_stop_list = end_obj.top_face_x.edges
        elif port_direction == 1:
            if start_obj.bottom_face_y:
                edge_start_list = start_obj.bottom_face_y.edges
            if end_obj.bottom_face_y:
                edge_stop_list = end_obj.bottom_face_y.edges
        elif port_direction == 4:
            if start_obj.top_face_y:
                edge_start_list = start_obj.top_face_y.edges
            if end_obj.top_face_y:
                edge_stop_list = end_obj.top_face_y.edges
        elif port_direction == 2:
            if start_obj.bottom_face_z:
                edge_start_list = start_obj.bottom_face_z.edges
            if end_obj.bottom_face_z:
                edge_stop_list = end_obj.bottom_face_z.edges
        elif port_direction == 5:
            if start_obj.top_face_z:
                edge_start_list = start_obj.top_face_z.edges
            if end_obj.top_face_z:
                edge_stop_list = end_obj.top_face_z.edges
        if not edge_start_list:
            edge_start_list = start_obj.edges
        if not edge_stop_list:
            edge_stop_list = end_obj.edges
        mindist = 1e6
        tol = 1e-12
        pos_tol = 1e-6
        edge_list = []
        actual_point = None
        is_parallel = False
        for el in edge_start_list:
            vertices_i = el.vertices
            vertex1_i = None
            vertex2_i = None
            if len(vertices_i) == 2:  # normal segment edge
                vertex1_i = vertices_i[0].position
                vertex2_i = vertices_i[1].position
                start_midpoint = el.midpoint
            elif len(vertices_i) == 1:
                # TODO why do we need this ?
                start_midpoint = vertices_i[0].position
            else:
                continue
            for el1 in edge_stop_list:
                vertices_j = el1.vertices
                vertex1_j = None
                vertex2_j = None
                if len(vertices_j) == 2:  # normal segment edge
                    vertex1_j = vertices_j[0].position
                    vertex2_j = vertices_j[1].position
                    end_midpoint = el1.midpoint
                elif len(vertices_j) == 1:
                    end_midpoint = vertices_j[0].position
                else:
                    continue

                parallel_edges = False
                vect = None
                if vertex1_i and vertex1_j:
                    if (
                        abs(
                            GeometryOperators._v_dot(
                                GeometryOperators.v_points(vertex1_i, vertex2_i),
                                GeometryOperators.v_points(vertex1_j, vertex2_j),
                            )
                        )
                        < tol
                    ):
                        continue  # skip perperndicular edges
                    if GeometryOperators.is_parallel(vertex1_i, vertex2_i, vertex1_j, vertex2_j):
                        parallel_edges = True
                    vert_dist_sum = GeometryOperators.arrays_positions_sum(
                        [vertex1_i, vertex2_i], [vertex1_j, vertex2_j]
                    )
                    vect = GeometryOperators.distance_vector(start_midpoint, vertex1_j, vertex2_j)
                else:
                    vert_dist_sum = GeometryOperators.arrays_positions_sum([start_midpoint], [end_midpoint])

                # dist = abs(_v_norm(vect))

                if parallel_edges:
                    pd1 = GeometryOperators.points_distance(vertex1_i, vertex2_i)
                    pd2 = GeometryOperators.points_distance(vertex1_j, vertex2_j)

                    if pd1 < pd2 and not GeometryOperators.is_projection_inside(
                        vertex1_i, vertex2_i, vertex1_j, vertex2_j
                    ):
                        continue
                    elif pd1 >= pd2 and not GeometryOperators.is_projection_inside(
                        vertex1_j, vertex2_j, vertex1_i, vertex2_i
                    ):
                        continue

                if actual_point is None:
                    edge_list = [el, el1]
                    is_parallel = parallel_edges
                    actual_point = GeometryOperators.find_point_on_plane([start_midpoint, end_midpoint], port_direction)
                    mindist = vert_dist_sum
                else:
                    new_point = GeometryOperators.find_point_on_plane([start_midpoint, end_midpoint], port_direction)
                    if (port_direction <= 2 and new_point - actual_point < 0) or (
                        port_direction > 2 and actual_point - new_point < 0
                    ):
                        edge_list = [el, el1]
                        is_parallel = parallel_edges
                        actual_point = new_point
                        mindist = vert_dist_sum
                    elif port_direction <= 2 and new_point - actual_point < tol and vert_dist_sum - mindist < pos_tol:
                        edge_list = [el, el1]
                        is_parallel = parallel_edges
                        actual_point = new_point
                        mindist = vert_dist_sum
                    elif port_direction > 2 and actual_point - new_point < tol and vert_dist_sum - mindist < pos_tol:
                        edge_list = [el, el1]
                        is_parallel = parallel_edges
                        actual_point = new_point
                        mindist = vert_dist_sum
        return edge_list, is_parallel

    @pyaedt_function_handler()
    def get_equivalent_parallel_edges(self, edgelist, portonplane=True, axisdir=0, startobj="", endobject=""):
        """Create two new edges that are parallel and equal to the smallest edge given a parallel couple of edges.

        Parameters
        ----------
        edgelist : list
            List of two parallel edges.
        portonplane : bool, optional
            Whether edges are to be on the plane orthogonal to the axis direction.
            The default is ``True``.
        axisdir : int, optional
            Axis direction. Choices are ``0`` through ``5``. The default is ``0``.
        startobj : str, optional
             Name of the starting object. The default is ``""``.
        endobject : str, optional
             Name of the ending object. The default is ``""``.

        Returns
        -------
        list
            List of two created edges.

        """
        if isinstance(edgelist[0], str):
            edgelist[0] = self.get_object_from_name(edgelist[0])
        if isinstance(edgelist[1], str):
            edgelist[1] = self.get_object_from_name(edgelist[1])

        l1 = edgelist[0].length
        l2 = edgelist[1].length
        if l1 < l2:
            orig_edge = edgelist[0]
            dest_edge = edgelist[1]
        else:
            orig_edge = edgelist[1]
            dest_edge = edgelist[0]

        first_edge = self.create_object_from_edge(orig_edge)
        second_edge = self.create_object_from_edge(orig_edge)
        ver1 = orig_edge.vertices
        ver2 = dest_edge.vertices
        if len(ver2) == 2:
            p = ver1[0].position
            a1 = ver2[0].position
            a2 = ver2[1].position
            vect = GeometryOperators.distance_vector(p, a1, a2)
            if portonplane:
                vect[divmod(axisdir, 3)[1]] = 0
            # TODO: can we avoid this translate operation - is there another way to check ?
            self.modeler.move(second_edge, vect)
            p_check = second_edge.vertices[0].position
            p_check2 = second_edge.vertices[1].position
        # elif len(ver2) == 1:  # for circular edges with one vertex
        #     p_check = first_edge.vertices[0].position
        #     p_check2 = second_edge.vertices[0].position
        else:
            self.delete(first_edge)
            self.delete(second_edge)
            return False

        obj_check = self.get_bodynames_from_position(p_check)
        obj_check2 = self.get_bodynames_from_position(p_check2)
        # if (startobj in obj_check and endobject in obj_check2) or (startobj in obj_check2 and endobject in obj_check):
        if (startobj in obj_check or endobject in obj_check) and (startobj in obj_check2 or endobject in obj_check2):
            if l1 < l2:
                return_edges = [first_edge, second_edge]
            else:
                return_edges = [second_edge, first_edge]
            return return_edges
        else:
            self.delete(second_edge)
            self.delete(first_edge)
            return None

    @pyaedt_function_handler()
    def get_object_faces(self, partId):
        """Retrieve the face IDs of a given object ID or object name.

        Parameters
        ----------
        partId : int or str
            Object ID or object name.

        Returns
        -------
        List
            List of faces IDs.

        References
        ----------

        >>> oEditor.GetFaceIDs

        """
        oFaceIDs = []
        if isinstance(partId, str) and partId in self.object_id_dict:
            oFaceIDs = self.oeditor.GetFaceIDs(partId)
            oFaceIDs = [int(i) for i in oFaceIDs]
        elif partId in self.objects:
            o = self.objects[partId]
            name = o.name
            oFaceIDs = self.oeditor.GetFaceIDs(name)
            oFaceIDs = [int(i) for i in oFaceIDs]
        return oFaceIDs

    @pyaedt_function_handler()
    def get_object_edges(self, partId):
        """Retrieve the edge IDs of a given object ID or object name.

        Parameters
        ----------
        partId : int or str
            Object ID or object name.

        Returns
        -------
        list
            List of edge IDs.

        References
        ----------

        >>> oEditor.GetEdgeIDsFromObject

        """
        oEdgeIDs = []
        if isinstance(partId, str) and partId in self.object_id_dict:
            oEdgeIDs = self.oeditor.GetEdgeIDsFromObject(partId)
            oEdgeIDs = [int(i) for i in oEdgeIDs]
        elif partId in self.objects:
            o = self.objects[partId]
            oEdgeIDs = self.oeditor.GetEdgeIDsFromObject(o.name)
            oEdgeIDs = [int(i) for i in oEdgeIDs]
        return oEdgeIDs

    @pyaedt_function_handler()
    def get_face_edges(self, partId):
        """Retrieve the edge IDs of a given face name or face ID.

        Parameters
        ----------
        partId : int or str
            Object ID or object name.

        Returns
        -------
        list
            List of edge IDs.

        References
        ----------

        >>> oEditor.GetEdgeIDsFromFace

        """
        oEdgeIDs = self.oeditor.GetEdgeIDsFromFace(partId)
        oEdgeIDs = [int(i) for i in oEdgeIDs]
        return oEdgeIDs

    @pyaedt_function_handler()
    def get_object_vertices(self, partID):
        """Retrieve the vertex IDs of a given object name or object ID.

        Parameters
        ----------
        partID : int or str
            Object ID or object name.

        Returns
        -------
        list
            List of vertex IDs.

        References
        ----------

        >>> oEditor.GetVertexIDsFromObject

        """
        oVertexIDs = []
        if isinstance(partID, str) and partID in self.object_id_dict:
            oVertexIDs = self.oeditor.GetVertexIDsFromObject(partID)
            oVertexIDs = [int(i) for i in oVertexIDs]
        elif partID in self.objects:
            o = self.objects[partID]
            oVertexIDs = self.oeditor.GetVertexIDsFromObject(o.name)
            oVertexIDs = [int(i) for i in oVertexIDs]
        return oVertexIDs

    @pyaedt_function_handler()
    def get_face_vertices(self, face_id):
        """Retrieve the vertex IDs of a given face ID or face name.

        Parameters
        ----------
        face_id : int or str
            Object ID or object name, which is available
            using the methods :func:`pyaedt.modeler.Primitives3D.Primitives3D.get_object_vertices`
            or :func:`pyaedt.modeler.Primitives2D.Primitives2D.get_object_vertices`.

        Returns
        -------
        list
            List of vertex IDs.

        References
        ----------

        >>> oEditor.GetVertexIDsFromFace

        """
        try:
            oVertexIDs = self.oeditor.GetVertexIDsFromFace(face_id)
        except:
            oVertexIDs = []
        else:
            oVertexIDs = [int(i) for i in oVertexIDs]
        return oVertexIDs

    @pyaedt_function_handler()
    def get_edge_length(self, edgeID):
        """Get the length of an edge.

        Parameters
        ----------
        edgeID : int
            ID of the edge.

        Returns
        -------
        type
            Edge length.

        """
        vertexID = self.get_edge_vertices(edgeID)
        pos1 = self.get_vertex_position(vertexID[0])
        if len(vertexID) < 2:
            return 0
        pos2 = self.get_vertex_position(vertexID[1])
        length = GeometryOperators.points_distance(pos1, pos2)
        return length

    @pyaedt_function_handler()
    def get_edge_vertices(self, edgeID):
        """Retrieve the vertex IDs of a given edge ID or edge name.

        Parameters
        ----------
        edgeID : int, str
            Object ID or object name, which is available using the
            methods :func:`pyaedt.modeler.Primitives3D.Primitives3D.get_object_vertices`
            or :func:`pyaedt.modeler.Primitives2D.Primitives2D.get_object_vertices`.

        Returns
        -------
        list
            List of vertex IDs.

        References
        ----------

        >>> oEditor.GetVertexIDsFromEdge

        """
        try:
            oVertexIDs = self.oeditor.GetVertexIDsFromEdge(edgeID)
        except:
            oVertexIDs = []
        else:
            oVertexIDs = [int(i) for i in oVertexIDs]
        return oVertexIDs

    @pyaedt_function_handler()
    def get_vertex_position(self, vertex_id):
        """Retrieve a vector of vertex coordinates.

        Parameters
        ----------
        vertex_id : int or str
            ID or name of the vertex.

        Returns
        -------
        list
            List of ``[x, y, z]`` coordinates indicating the position.

        References
        ----------

        >>> oEditor.GetVertexPosition

        """
        try:
            pos = self.oeditor.GetVertexPosition(vertex_id)
        except:
            position = []
        else:
            position = [float(i) for i in pos]
        return position

    @pyaedt_function_handler()
    def get_face_area(self, face_id):
        """Retrieve the area of a given face ID.

        Parameters
        ----------
        face_id : int
            ID of the face.

        Returns
        -------
        float
            Value for the face area.

        References
        ----------

        >>> oEditor.GetFaceArea

        """

        area = self.oeditor.GetFaceArea(face_id)
        return area

    @pyaedt_function_handler()
    def get_face_center(self, face_id):
        """Retrieve the center position for a given planar face ID.

        Parameters
        ----------
        face_id : int
            ID of the face.

        Returns
        -------
        list
            A list of ``[x, y, z]`` coordinates for the
            planar face center position.

        References
        ----------

        >>> oEditor.GetFaceCenter

        """
        try:
            c = self.oeditor.GetFaceCenter(face_id)
        except:
            self.logger.warning("Non Planar Faces doesn't provide any Face Center")
            return False
        center = [float(i) for i in c]
        return center

    @pyaedt_function_handler()
    def get_mid_points_on_dir(self, sheet, axisdir):
        """Retrieve midpoints on a given axis direction.

        Parameters
        ----------
        sheet :

        axisdir : int
            Axis direction. Choices are ``0`` through ``5``.

        Returns
        -------
        type

        """
        edgesid = self.get_object_edges(sheet)
        id = divmod(axisdir, 3)[1]
        midpoint_array = []
        for ed in edgesid:
            midpoint_array.append(self.get_edge_midpoint(ed))
        point0 = []
        point1 = []
        for el in midpoint_array:
            if not point0:
                point0 = el
                point1 = el
            elif axisdir < 3 and el[id] < point0[id] or axisdir > 2 and el[id] > point0[id]:
                point0 = el
            elif axisdir < 3 and el[id] > point1[id] or axisdir > 2 and el[id] < point1[id]:
                point1 = el
        return point0, point1

    @pyaedt_function_handler()
    def get_edge_midpoint(self, partID):
        """Retrieve the midpoint coordinates of a given edge ID or edge name.

        Parameters
        ----------
        partID : int or str
            Object ID  or object name.

        Returns
        -------
        list
            List of midpoint coordinates. If the edge is not a segment with
            two vertices, an empty list is returned.
        """

        if isinstance(partID, str) and partID in self.object_id_dict:
            partID = self.object_id_dict[partID]

        if partID in self.objects and self.objects[partID].object_type == "Line":
            vertices = self.get_object_vertices(partID)
        else:
            try:
                vertices = self.get_edge_vertices(partID)
            except:
                vertices = []
        if len(vertices) == 2:
            vertex1 = self.get_vertex_position(vertices[0])
            vertex2 = self.get_vertex_position(vertices[1])
            midpoint = GeometryOperators.get_mid_point(vertex1, vertex2)
            return list(midpoint)
        elif len(vertices) == 1:
            return list(self.get_vertex_position(vertices[0]))
        else:
            return []

    @pyaedt_function_handler()
    def get_bodynames_from_position(self, position, units=None):
        """Retrieve the names of the objects that are in contact with a given point.

        Parameters
        ----------
        position : list
            List of ``[x, y, z]`` coordinates for the point.
        units : str, optional
            Units, such as ``"m"``. The default is ``None``, in which case the
            model units are used.

        Returns
        -------
        list
            List of object names.

        References
        ----------

        >>> oEditor.GetBodyNamesByPosition

        """
        XCenter, YCenter, ZCenter = self._pos_with_arg(position, units)
        vArg1 = ["NAME:Parameters"]
        vArg1.append("XPosition:="), vArg1.append(XCenter)
        vArg1.append("YPosition:="), vArg1.append(YCenter)
        vArg1.append("ZPosition:="), vArg1.append(ZCenter)
        list_of_bodies = list(self.oeditor.GetBodyNamesByPosition(vArg1))
        return list_of_bodies

    @pyaedt_function_handler()
    def get_edgeid_from_position(self, position, obj_name=None, units=None):
        """Get an edge ID from a position.

        Parameters
        ----------
        position : list
            List of ``[x, y, z]`` coordinates for the position.
        obj_name : str, optional
            Name of the object. The default is ``None``, in which case all
            objects are searched.
        units : str, optional
            Units for the position, such as ``"m"``. The default is ``None``,
            in which case the model units are used.

        Returns
        -------
        type
            Edge ID of the first object touching this position.
        """
        if isinstance(obj_name, str):
            object_list = [obj_name]
        else:
            object_list = self.object_names

        edgeID = -1
        XCenter, YCenter, ZCenter = self._pos_with_arg(position, units)

        vArg1 = ["NAME:EdgeParameters"]
        vArg1.append("BodyName:="), vArg1.append("")
        vArg1.append("XPosition:="), vArg1.append(XCenter)
        vArg1.append("YPosition:="), vArg1.append(YCenter)
        vArg1.append("ZPosition:="), vArg1.append(ZCenter)
        for obj in object_list:
            vArg1[2] = obj
            try:
                edgeID = int(self.oeditor.GetEdgeByPosition(vArg1))
                return edgeID
            except:
                pass

    @pyaedt_function_handler()
    def get_edgeids_from_vertexid(self, vertexid, obj_name):
        """Retrieve edge IDs for a vertex ID.

        Parameters
        ----------
        vertexid : int
            Vertex ID.
        obj_name :
            Name of the object.

        Returns
        -------
        List
            List of edge IDs for the vertex ID.

        References
        ----------

        >>> oEditor.GetEdgeIDsFromObject
        >>> oEditor.GetVertexIDsFromEdge

        """
        edgeID = []
        edges = self.get_object_edges(obj_name)
        for edge in edges:
            vertx = self.get_edge_vertices(edge)
            if vertexid in vertx:
                edgeID.append(edge)

        return edgeID

    @pyaedt_function_handler()
    def get_faceid_from_position(self, position, obj_name=None, units=None):
        """Retrieve a face ID from a position.

        Parameters
        ----------
        position : list
            List of ``[x, y, z]`` coordinates for the position.
        obj_name : str, optional
            Name of the object. The default is ``None``, in which case all
            objects are searched.
        units : str, optional
            Units, such as ``"m"``. The default is ``None``, in which case the
            model units are used.

        Returns
        -------
        int
            Face ID of the first object touching this position.

        References
        ----------

        >>> oEditor.GetFaceByPosition

        """
        if isinstance(obj_name, str):
            object_list = [obj_name]
        else:
            object_list = self.object_names

        XCenter, YCenter, ZCenter = self._pos_with_arg(position, units)
        vArg1 = ["NAME:FaceParameters"]
        vArg1.append("BodyName:="), vArg1.append("")
        vArg1.append("XPosition:="), vArg1.append(XCenter)
        vArg1.append("YPosition:="), vArg1.append(YCenter)
        vArg1.append("ZPosition:="), vArg1.append(ZCenter)
        for obj in object_list:
            vArg1[2] = obj
            try:
                face_id = self.oeditor.GetFaceByPosition(vArg1)
                return face_id
            except:
                # Not Found, keep looking
                pass

    @pyaedt_function_handler()
    def get_edges_on_bounding_box(self, sheets, return_colinear=True, tol=1e-6):
        """Retrieve the edges of the sheets passed in the input that are lying on the bounding box.

        This method creates new lines for the detected edges and returns the IDs of these lines.
        If required, only colinear edges are returned.

        Parameters
        ----------
        sheets : int, str, or list
            ID or name for one or more sheets.
        return_colinear : bool, optional
            Whether to return only colinear edges. The default is ``True``.
            If ``False``, all edges on the bounding box are returned.
        tol : float, optional
            Geometric tolerance. The default is ``1e-6``.

        Returns
        -------
        list
            List of edge IDs lying on the bounding box.

        """
        port_sheets = self._modeler.convert_to_selections(sheets, return_list=True)
        bb = self._modeler.get_model_bounding_box()

        candidate_edges = []
        for p in port_sheets:
            edges = self[p].edges
            for edge in edges:
                vertices = edge.vertices
                v_flag = False
                for vertex in vertices:
                    v = vertex.position
                    xyz_flag = 0
                    if abs(v[0] - bb[0]) < tol or abs(v[0] - bb[3]) < tol:
                        xyz_flag += 1
                    if abs(v[1] - bb[1]) < tol or abs(v[1] - bb[4]) < tol:
                        xyz_flag += 1
                    if abs(v[2] - bb[2]) < tol or abs(v[2] - bb[5]) < tol:
                        xyz_flag += 1
                    if xyz_flag >= 2:
                        v_flag = True
                    else:
                        v_flag = False
                        break
                if v_flag:
                    candidate_edges.append(edge)

        if not return_colinear:
            return candidate_edges

        selected_edges = []
        for i, edge_i in enumerate(candidate_edges[:-1]):
            vertex1_i = edge_i.vertices[0].position
            midpoint_i = edge_i.midpoint
            for j, edge_j in enumerate(candidate_edges[i + 1 :]):
                midpoint_j = edge_j.midpoint
                area = GeometryOperators.get_triangle_area(midpoint_i, midpoint_j, vertex1_i)
                if area < tol**2:
                    selected_edges.extend([edge_i, edge_j])
                    break
        selected_edges = list(set(selected_edges))

        for edge in selected_edges:
            self.create_object_from_edge(edge)
            time.sleep(aedt_wait_time)

        return selected_edges

    @pyaedt_function_handler()
    def get_edges_for_circuit_port_from_sheet(
        self, sheet, XY_plane=True, YZ_plane=True, XZ_plane=True, allow_perpendicular=False, tol=1e-6
    ):
        """Retrieve two edge IDs that are suitable for a circuit port from a sheet.

        One edge belongs to the sheet passed in the input, and the second edge
        is the closest edge's coplanar to the first edge (aligned to the XY, YZ,
        or XZ plane). This method creates new lines for the detected edges and returns
        the IDs of these lines.

        This method accepts one or more sheet objects as input,
        while the method :func:`Primitives.get_edges_for_circuit_port`
        accepts a face ID.

        Parameters
        ----------
        sheet : int, str, or list
            ID or name for one or more sheets.
        XY_plane : bool, optional
            Whether the edge's pair are to be on the XY plane.
            The default is ``True``.
        YZ_plane : bool, optional
            Whether the edge's pair are to be on the YZ plane.
            The default is ``True``.
        XZ_plane : bool, optional
            Whether the edge's pair are to be on the XZ plane.
            The default is ``True``.
        allow_perpendicular : bool, optional
            Whether the edge's pair are to be perpendicular.
            The default is ``False``.
        tol : float, optional
            Geometric tolerance. The default is ``1e-6``.

        Returns
        -------
        list
            List of edge IDs.

        """
        tol2 = tol**2
        port_sheet = self._modeler.convert_to_selections(sheet, return_list=True)
        if len(port_sheet) > 1:
            return []
        else:
            port_sheet = port_sheet[0]
        port_edges = self.get_object_edges(port_sheet)

        # find the bodies to exclude
        port_sheet_midpoint = self.get_face_center(self.get_object_faces(port_sheet)[0])
        point = self._modeler.Position(*port_sheet_midpoint)
        list_of_bodies = self.get_bodynames_from_position(point)

        # select all edges
        all_edges = []
        solids = [s for s in self.solid_names if s not in list_of_bodies]
        for solid in solids:
            edges = self.get_object_edges(solid)
            all_edges.extend(edges)
        all_edges = list(set(all_edges))  # remove duplicates

        # select edges coplanar to port edges (aligned to XY, YZ, or XZ plane)
        ux = [1.0, 0.0, 0.0]
        uy = [0.0, 1.0, 0.0]
        uz = [0.0, 0.0, 1.0]
        midpoints = {}
        candidate_edges = []
        for ei in port_edges:
            vertices_i = self.get_edge_vertices(ei)
            if len(vertices_i) == 1:  # maybe a circle
                vertex1_i = self.get_vertex_position(vertices_i[0])
                area_i = self.get_face_area(self.get_object_faces(port_sheet)[0])
                if area_i is None or area_i < tol2:  # degenerated face
                    continue
                center_i = self.get_face_center(self.get_object_faces(port_sheet)[0])
                if not center_i:  # non planar face
                    continue
                radius_i = GeometryOperators.points_distance(vertex1_i, center_i)
                area_i_eval = math.pi * radius_i**2
                if abs(area_i - area_i_eval) < tol2:  # it is a circle
                    vertex2_i = center_i
                    midpoints[ei] = center_i
                else:  # not a circle
                    continue
            elif len(vertices_i) == 2:  # normal segment edge
                vertex1_i = self.get_vertex_position(vertices_i[0])
                vertex2_i = self.get_vertex_position(vertices_i[1])
                midpoints[ei] = self.get_edge_midpoint(ei)
            else:  # undetermined edge --> skip
                continue
            for ej in all_edges:
                vertices_j = self.get_edge_vertices(ej)
                if len(vertices_j) == 1:  # edge is an arc, not supported
                    continue
                elif len(vertices_j) == 2:  # normal segment edge
                    vertex1_j = self.get_vertex_position(vertices_j[0])
                    vertex2_j = self.get_vertex_position(vertices_j[1])
                else:  # undetermined edge --> skip
                    continue

                if (
                    not allow_perpendicular
                    and abs(
                        GeometryOperators._v_dot(
                            GeometryOperators.v_points(vertex1_i, vertex2_i),
                            GeometryOperators.v_points(vertex1_j, vertex2_j),
                        )
                    )
                    < tol
                ):
                    continue

                normal1 = GeometryOperators.v_cross(
                    GeometryOperators.v_points(vertex1_i, vertex2_i), GeometryOperators.v_points(vertex1_i, vertex1_j)
                )
                normal1_norm = GeometryOperators.v_norm(normal1)
                if YZ_plane and abs(abs(GeometryOperators._v_dot(normal1, ux)) - normal1_norm) < tol:
                    pass
                elif XZ_plane and abs(abs(GeometryOperators._v_dot(normal1, uy)) - normal1_norm) < tol:
                    pass
                elif XY_plane and abs(abs(GeometryOperators._v_dot(normal1, uz)) - normal1_norm) < tol:
                    pass
                else:
                    continue

                vec1 = GeometryOperators.v_points(vertex1_i, vertex2_j)
                if abs(GeometryOperators._v_dot(normal1, vec1)) < tol2:  # the 4th point is coplanar
                    candidate_edges.append(ej)

        minimum_distance = tol**-1
        selected_edges = []
        for ei in midpoints:
            midpoint_i = midpoints[ei]
            for ej in candidate_edges:
                midpoint_j = self.get_edge_midpoint(ej)
                d = GeometryOperators.points_distance(midpoint_i, midpoint_j)
                if d < minimum_distance:
                    minimum_distance = d
                    selected_edges = [ei, ej]

        if selected_edges:
            new_edge1 = self.create_object_from_edge(selected_edges[0])
            time.sleep(aedt_wait_time)
            new_edge2 = self.create_object_from_edge(selected_edges[1])
            return selected_edges
        else:
            return []
        pass

    @pyaedt_function_handler()
    def get_edges_for_circuit_port(
        self, face_id, XY_plane=True, YZ_plane=True, XZ_plane=True, allow_perpendicular=False, tol=1e-6
    ):
        """Retrieve two edge IDs suitable for the circuit port.

        One edge belongs to the face ID passed in the input, and the second edge
        is the closest edge's coplanar to the first edge (aligned to the XY, YZ,
        or XZ plane). This method creates new lines for the detected edges and returns
        the IDs of these lines.

        This method accepts a face ID in the input, while the `get_edges_for_circuit_port_from_port`
        method accepts one or more sheet objects.

        Parameters
        ----------
        face_id :
            ID of the face.
        XY_plane : bool, optional
            Whether the edge's pair are to be on the XY plane.
            The default is ``True``.
        YZ_plane : bool, optional
            Whether the edge's pair are to be on the YZ plane.
            The default is ``True``.
        XZ_plane : bool, optional
            Whether the edge's pair are to be on the XZ plane.
            The default is ``True``.
        allow_perpendicular : bool, optional
            Whether the edge's pair are to be perpendicular.
            The default is ``False``.
        tol : float, optional
            Geometric tolerance. The default is ``1e-6``.

        Returns
        -------
        list
            List of edge IDs.

        """
        tol2 = tol**2

        port_edges = self.get_face_edges(face_id)

        # find the bodies to exclude
        port_sheet_midpoint = self.get_face_center(face_id)
        point = self._modeler.Position(port_sheet_midpoint)
        list_of_bodies = self.get_bodynames_from_position(point)

        # select all edges
        all_edges = []
        solids = [s for s in self.solid_names if s not in list_of_bodies]
        for solid in solids:
            edges = self.get_object_edges(solid)
            all_edges.extend(edges)
        all_edges = list(set(all_edges))  # remove duplicates

        # select edges coplanar to port edges (aligned to XY, YZ, or XZ plane)
        ux = [1.0, 0.0, 0.0]
        uy = [0.0, 1.0, 0.0]
        uz = [0.0, 0.0, 1.0]
        midpoints = {}
        candidate_edges = []
        for ei in port_edges:
            vertices_i = self.get_edge_vertices(ei)
            if len(vertices_i) == 1:  # maybe a circle
                vertex1_i = self.get_vertex_position(vertices_i[0])
                area_i = self.get_face_area(face_id)
                if area_i is None or area_i < tol2:  # degenerated face
                    continue
                center_i = self.get_face_center(face_id)
                if not center_i:  # non planar face
                    continue
                radius_i = GeometryOperators.points_distance(vertex1_i, center_i)
                area_i_eval = math.pi * radius_i**2
                if abs(area_i - area_i_eval) < tol2:  # it is a circle
                    vertex2_i = center_i
                    midpoints[ei] = center_i
                else:  # not a circle
                    continue
            elif len(vertices_i) == 2:  # normal segment edge
                vertex1_i = self.get_vertex_position(vertices_i[0])
                vertex2_i = self.get_vertex_position(vertices_i[1])
                midpoints[ei] = self.get_edge_midpoint(ei)
            else:  # undetermined edge --> skip
                continue
            for ej in all_edges:
                vertices_j = self.get_edge_vertices(ej)
                if len(vertices_j) == 1:  # edge is an arc, not supported
                    continue
                elif len(vertices_j) == 2:  # normal segment edge
                    vertex1_j = self.get_vertex_position(vertices_j[0])
                    vertex2_j = self.get_vertex_position(vertices_j[1])
                else:  # undetermined edge --> skip
                    continue

                if (
                    not allow_perpendicular
                    and abs(
                        GeometryOperators._v_dot(
                            GeometryOperators.v_points(vertex1_i, vertex2_i),
                            GeometryOperators.v_points(vertex1_j, vertex2_j),
                        )
                    )
                    < tol
                ):
                    continue

                normal1 = GeometryOperators.v_cross(
                    GeometryOperators.v_points(vertex1_i, vertex2_i), GeometryOperators.v_points(vertex1_i, vertex1_j)
                )
                normal1_norm = GeometryOperators.v_norm(normal1)
                if YZ_plane and abs(abs(GeometryOperators._v_dot(normal1, ux)) - normal1_norm) < tol:
                    pass
                elif XZ_plane and abs(abs(GeometryOperators._v_dot(normal1, uy)) - normal1_norm) < tol:
                    pass
                elif XY_plane and abs(abs(GeometryOperators._v_dot(normal1, uz)) - normal1_norm) < tol:
                    pass
                else:
                    continue

                vec1 = GeometryOperators.v_points(vertex1_i, vertex2_j)
                if abs(GeometryOperators._v_dot(normal1, vec1)) < tol2:  # the 4th point is coplanar
                    candidate_edges.append(ej)

        minimum_distance = tol**-1
        selected_edges = []
        for ei in midpoints:
            midpoint_i = midpoints[ei]
            for ej in candidate_edges:
                midpoint_j = self.get_edge_midpoint(ej)
                d = GeometryOperators.points_distance(midpoint_i, midpoint_j)
                if d < minimum_distance:
                    minimum_distance = d
                    selected_edges = [ei, ej]

        if selected_edges:
            new_edge1 = self.create_object_from_edge(selected_edges[0])
            time.sleep(aedt_wait_time)
            new_edge2 = self.create_object_from_edge(selected_edges[1])
            return selected_edges
        else:
            return []
        pass

    @pyaedt_function_handler()
    def get_closest_edgeid_to_position(self, position, units=None):
        """Get the edge ID closest to a given position.

        Parameters
        ----------
        position : list
            List of ``[x,y,z]`` coordinates for the position.
        units :
            Units for the position, such as ``"m"``. The default is ``None``, which means the model units are used.

        Returns
        -------
        int
            Edge ID of the edge closest to this position.

        """
        if isinstance(position, list):
            position = self.modeler.Position(position)

        bodies = self.get_bodynames_from_position(position, units)
        # the function searches in all bodies, not efficient
        face_id = self.get_faceid_from_position(position, obj_name=bodies[0], units=units)
        edges = self.get_face_edges(face_id)
        distance = 1e6
        selected_edge = None
        for edge in edges:
            midpoint = self.get_edge_midpoint(edge)
            if self.model_units == "mm" and units == "meter":
                midpoint = [i / 1000 for i in midpoint]
            elif self.model_units == "meter" and units == "mm":
                midpoint = [i * 1000 for i in midpoint]
            d = GeometryOperators.points_distance(midpoint, [position.X, position.Y, position.Z])
            if d < distance:
                selected_edge = int(edge)
                distance = d
        return selected_edge

    @pyaedt_function_handler()
    def _resolve_object(self, object):
        if isinstance(object, Object3d):
            return object
        else:
            return self[object]

    @pyaedt_function_handler()
    def _get_model_objects(self, model=True):
        """Retrieve all model objects.

        Parameters
        ----------
        model : bool, optional
            Whether to retrieve all model objects. The default is ``True``. When ``False``,
            all non-model objects are retrieved.

        Returns
        -------
        list
            List of retrieved objects.

        """
        list_objs = []
        for id, obj in self.objects.items():
            if obj.model == model:
                list_objs.append(obj.name)
        return list_objs

    @pyaedt_function_handler()
    def _check_material(self, matname, defaultmatname):
        """Check for a material name.

        If a material name exists, it is assigned. Otherwise, the material
        specified as the default is assigned.

        Parameters
        ----------
        matname : str
            Name of the material.
        defaultmatname : str
            Name of the default material to assign if ``metname`` does not exist.

        Returns
        -------
        str or bool
            String if a material name, Boolean if the material is a dielectric.

        """
        if isinstance(matname, Material):
            if self._app._design_type == "HFSS":
                return matname.name, matname.is_dielectric()
            else:
                return matname.name, True
        if matname:
            if self._app.materials[matname]:
                if self._app._design_type == "HFSS":
                    return self._app.materials[matname].name, self._app.materials[matname].is_dielectric()
                else:
                    return self._app.materials[matname].name, True
            else:
                self.logger.warning("Material %s doesn not exists. Assigning default material", matname)
        if self._app._design_type == "HFSS":
            return defaultmatname, self._app.materials.material_keys[defaultmatname].is_dielectric()
        else:
            return defaultmatname, True

    @pyaedt_function_handler()
    def _refresh_solids(self):
        test = list(self.oeditor.GetObjectsInGroup("Solids"))
        if test is None or test is False:
            assert False, "Get Solids is failing"
        elif test is True:
            self._solids = []  # In IronPython True is returned when no sheets are present
        else:
            self._solids = list(test)
        self._all_object_names = self._solids + self._sheets + self._lines + self._points

    @pyaedt_function_handler()
    def _refresh_sheets(self):
        test = list(self.oeditor.GetObjectsInGroup("Sheets"))
        if test is None or test is False:
            assert False, "Get Sheets is failing"
        elif test is True:
            self._sheets = []  # In IronPython True is returned when no sheets are present
        else:
            self._sheets = list(test)
        self._all_object_names = self._solids + self._sheets + self._lines + self._points

    @pyaedt_function_handler()
    def _refresh_lines(self):
        test = list(self.oeditor.GetObjectsInGroup("Lines"))
        if test is None or test is False:
            assert False, "Get Lines is failing"
        elif test is True:
            self._lines = []  # In IronPython True is returned when no lines are present
        else:
            self._lines = list(test)
        self._all_object_names = self._solids + self._sheets + self._lines + self._points

    @pyaedt_function_handler()
    def _refresh_points(self):
        test = list(self.oeditor.GetObjectsInGroup("Points"))
        if test is None or test is False:
            assert False, "Get Points is failing"
        elif test is True:
            self._points = []  # In IronPython True is returned when no points are present
        else:
            self._points = list(test)
        self._all_object_names = self._solids + self._sheets + self._lines + self._points

    @pyaedt_function_handler()
    def _refresh_unclassified(self):
        test = _retry_ntimes(10, self.oeditor.GetObjectsInGroup, "Unclassified")
        if test is None or test is False:
            self._unclassified = []
            self.logger.debug("Unclassified is failing")
        elif test is True:
            self._unclassified = []  # In IronPython True is returned when no unclassified are present
        else:
            self._unclassified = list(test)

    @pyaedt_function_handler()
    def _refresh_object_types(self):
        self._refresh_solids()
        self._refresh_sheets()
        self._refresh_lines()
        self._refresh_points()
        self._refresh_unclassified()
        self._all_object_names = self._solids + self._sheets + self._lines + self._points + self._unclassified

    @pyaedt_function_handler()
    def _create_object(self, name):
        o = Object3d(self, name)
        new_id = o.id
        self.objects[new_id] = o
        self.object_id_dict[o.name] = new_id
        return o

    @pyaedt_function_handler()
    def _create_user_defined_component(self, name):
        o = UserDefinedComponent(self, name)
        self.user_defined_components[name] = o
        return o

    @pyaedt_function_handler()
    def _create_point(self, name):
        point = Point(self, name)
        self._point_names[name] = point
        self._points.append(point)
        return point

    @pyaedt_function_handler()
    def _refresh_all_ids_from_aedt_file(self):
        if not self._app.design_properties or "ModelSetup" not in self._app.design_properties:
            return False

        try:
            groups = self._app.design_properties["ModelSetup"]["GeometryCore"]["GeometryOperations"]["Groups"]["Group"]
        except KeyError:
            groups = []
        if not isinstance(groups, list):
            groups = [groups]
        try:
            self._app.design_properties["ModelSetup"]["GeometryCore"]["GeometryOperations"]["ToplevelParts"][
                "GeometryPart"
            ]
        except KeyError:
            return 0
        for el in self._app.design_properties["ModelSetup"]["GeometryCore"]["GeometryOperations"]["ToplevelParts"][
            "GeometryPart"
        ]:
            if isinstance(el, (OrderedDict, dict)):
                attribs = el["Attributes"]
            else:
                attribs = self._app.design_properties["ModelSetup"]["GeometryCore"]["GeometryOperations"][
                    "ToplevelParts"
                ]["GeometryPart"]["Attributes"]
            if attribs["Name"] in self._all_object_names:
                o = self._create_object(name=attribs["Name"])
                o._part_coordinate_system = attribs["PartCoordinateSystem"]
                if "NonModel" in attribs["Flags"]:
                    o._model = False
                else:
                    o._model = True
                if "Wireframe" in attribs["Flags"]:
                    o._wireframe = True
                else:
                    o._wireframe = False
                groupname = ""
                for group in groups:
                    if attribs["GroupId"] == group["GroupID"]:
                        groupname = group["Attributes"]["Name"]

                o._m_groupName = groupname
                try:
                    o._color = tuple(int(x) for x in attribs["Color"][1:-1].split(" "))
                except:
                    o._color = None
                o._surface_material = attribs.get("SurfaceMaterialValue", None)
                if o._surface_material:
                    o._surface_material = o._surface_material[1:-1].lower()
                if "MaterialValue" in attribs:
                    o._material_name = attribs["MaterialValue"][1:-1].lower()
                else:
                    o._material_name = attribs.get("MaterialName", None)

                o._is_updated = True
        return len(self.objects)

    @pyaedt_function_handler()
    def _default_object_attributes(self, name=None, matname=None, flags=""):

        if not matname:
            matname = self.defaultmaterial

        material, is_dielectric = self._check_material(matname, self.defaultmaterial)

        solve_inside = False
        if is_dielectric:
            solve_inside = True

        if not name:
            name = _uname()
        try:
            color = str(tuple(self._app.materials.material_keys[material].material_appearance)).replace(",", " ")
        except:
            color = "(132 132 193)"
        if material in ["vacuum", "air", "glass", "water_distilled", "water_fresh", "water_sea"]:
            transparency = 0.8
        else:
            transparency = 0.2
        args = [
            "NAME:Attributes",
            "Name:=",
            name,
            "Flags:=",
            flags,
            "Color:=",
            color,
            "Transparency:=",
            transparency,
            "PartCoordinateSystem:=",
            "Global",
            "SolveInside:=",
            solve_inside,
        ]

        if self.version >= "2019.3":
            args += [
                "MaterialValue:=",
                chr(34) + material + chr(34),
                "UDMId:=",
                "",
                "SurfaceMaterialValue:=",
                chr(34) + "Steel-oxidised-surface" + chr(34),
            ]
        else:
            args += ["MaterialName:=", material]

        if self.version >= "2021.2":
            args += [
                "ShellElement:=",
                False,
                "ShellElementThickness:=",
                "0mm",
                "IsMaterialEditable:=",
                True,
                "UseMaterialAppearance:=",
                False,
                "IsLightweight:=",
                False,
            ]

        return args

    @pyaedt_function_handler()
    def _crosssection_arguments(self, type, orient, width, topwidth, height, num_seg, bend_type=None):
        """Generate the properties array for the polyline cross-section."""
        arg_str = ["NAME:PolylineXSection"]

        # Set the default section type to "None"
        section_type = type
        if not section_type:
            section_type = "None"

        # Set the default orientation to "Auto"
        section_orient = orient
        if not section_orient:
            section_orient = "Auto"

        # Set the default bend-type to "Corner"
        section_bend = bend_type
        if not section_bend:
            section_bend = "Corner"

        # Ensure number-of segments is valid
        if num_seg:
            assert num_seg > 2, "Number of segments for a cross-section must be 0 or greater than 2."

        model_units = self.model_units
        arg_str += ["XSectionType:=", section_type]
        arg_str += ["XSectionOrient:=", section_orient]
        arg_str += ["XSectionWidth:=", _dim_arg(width, model_units)]
        arg_str += ["XSectionTopWidth:=", _dim_arg(topwidth, model_units)]
        arg_str += ["XSectionHeight:=", _dim_arg(height, model_units)]
        arg_str += ["XSectionNumSegments:=", "{}".format(num_seg)]
        arg_str += ["XSectionBendType:=", section_bend]

        return arg_str

    @pyaedt_function_handler()
    def _arg_with_dim(self, value, units=None):
        if isinstance(value, str):
            val = value
        else:
            if units is None:
                units = self.model_units
            val = "{0}{1}".format(value, units)

        return val

    @pyaedt_function_handler()
    def _pos_with_arg(self, pos, units=None):
        xpos = self._arg_with_dim(pos[0], units)
        if len(pos) < 2:
            ypos = self._arg_with_dim(0, units)
        else:
            ypos = self._arg_with_dim(pos[1], units)
        if len(pos) < 3:
            zpos = self._arg_with_dim(0, units)
        else:
            zpos = self._arg_with_dim(pos[2], units)

        return xpos, ypos, zpos

    @pyaedt_function_handler()
    def _str_list(self, theList):
        szList = ""
        for id in theList:
            o = self.objects[id]
            if len(szList):
                szList += ","
            szList += str(o.name)

        return szList

    @pyaedt_function_handler()
    def _find_object_from_edge_id(self, lval):
        objList = []
        objListSheets = self.sheet_names
        if len(objListSheets) > 0:
            objList.extend(objListSheets)
        objListSolids = self.solid_names
        if len(objListSolids) > 0:
            objList.extend(objListSolids)
        for obj in objList:
            val = _retry_ntimes(10, self.oeditor.GetEdgeIDsFromObject, obj)
            if not (isinstance(val, bool)) and str(lval) in list(val):
                return obj
        return None

    @pyaedt_function_handler()
    def _find_object_from_face_id(self, lval):
        if self.oeditor is not None:
            objList = []
            objListSheets = self.sheet_names
            if len(objListSheets) > 0:
                objList.extend(objListSheets)
            objListSolids = self.solid_names
            if len(objListSolids) > 0:
                objList.extend(objListSolids)
            for obj in objList:
                face_ids = list(self.oeditor.GetFaceIDs(obj))
                if str(lval) in face_ids:
                    return obj

        return None

    @pyaedt_function_handler()
    def _get_user_defined_component_names(self):
        """Get list of names for user-defined models.

        Returns
        -------
        list
           List of names for user-defined models.
        """
        udm_lists = []
        if self._app.design_properties and self._app.design_properties.get("ModelSetup", None):
            try:
                entity_list = self._app.design_properties["ModelSetup"]["GeometryCore"]["GeometryOperations"][
                    "UserDefinedModels"
                ]
                if entity_list:
                    udm_entry = entity_list["UserDefinedModel"]
                    if isinstance(udm_entry, (dict, OrderedDict)):
                        udm_entry = [udm_entry]
                    for data in udm_entry:
                        udm_lists.append(data["Attributes"]["Name"])
            except:
                self.logger.error("User-defined models were not retrieved from the AEDT file.")
        return udm_lists

    @pyaedt_function_handler()
    def __getitem__(self, partId):
        """Get the object ``Object3D`` for a given object ID or object name.

        Parameters
        ----------
        partId : int or str
            Object ID or object name from the 3D modeler.

        Returns
        -------
        :class:`pyaedt.modeler.Object3d.Object3d`
            Returns None if the part ID or the object name is not found.

        """
        if isinstance(partId, int):
            if partId in self.objects:
                return self.objects[partId]
        elif partId in self.object_id_dict:
            return self.objects[self.object_id_dict[partId]]
        elif partId in self.user_defined_components:
            return self.user_defined_components[partId]
        elif isinstance(partId, Object3d) or isinstance(partId, UserDefinedComponent):
            return partId
        return None
