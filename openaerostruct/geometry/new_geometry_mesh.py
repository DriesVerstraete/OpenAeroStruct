""" Manipulate geometry mesh based on high-level design parameters. """

from __future__ import division, print_function
import numpy as np
from numpy import cos, sin, tan

from openaerostruct.geometry.utils import \
    rotate, scale_x, shear_x, shear_y, shear_z, \
    sweep, dihedral, stretch, taper

from openmdao.api import ExplicitComponent
from openaerostruct.structures.utils import radii

try:
    from openaerostruct.fortran import OAS_API
    fortran_flag = True
    data_type = float
except:
    fortran_flag = False
    data_type = complex


class GeometryMesh(ExplicitComponent):
    """
    OpenMDAO component that performs mesh manipulation functions. It reads in
    the initial mesh from the surface dictionary and outputs the altered
    mesh based on the geometric design variables.

    Depending on the design variables selected or the supplied geometry information,
    only some of the follow parameters will actually be given to this component.
    If parameters are not active (they do not deform the mesh), then
    they will not be given to this component.

    Parameters
    ----------
    sweep : float
        Shearing sweep angle in degrees.
    dihedral : float
        Dihedral angle in degrees.
    twist[ny] : numpy array
        1-D array of rotation angles for each wing slice in degrees.
    chord_dist[ny] : numpy array
        Chord length for each panel edge.
    taper : float
        Taper ratio for the wing; 1 is untapered, 0 goes to a point at the tip.

    Returns
    -------
    mesh[nx, ny, 3] : numpy array
        Modified mesh based on the initial mesh in the surface dictionary and
        the geometric design variables.
    """

    def initialize(self):
        self.metadata.declare('surface', type_=dict, required=True)

    def setup(self):
        surface = self.metadata['surface']

        ny = surface['num_y']
        self.mesh = surface['mesh']

        # Compute span. We need .real to make span to avoid OpenMDAO warnings.
        quarter_chord = 0.25 * self.mesh[-1] + 0.75 * self.mesh[0]
        span = max(quarter_chord[:, 1]).real - min(quarter_chord[:, 1]).real
        if surface['symmetry']:
            span *= 2.

        self.geo_params = geo_params = {}

        geo_params['taper'] = 1.
        geo_params['sweep'] = 0.
        geo_params['dihedral'] = 0.
        geo_params['span'] = span
        geo_params['chord'] = np.ones(ny)
        geo_params['twist'] = np.zeros(ny)
        geo_params['xshear'] = np.zeros(ny)
        geo_params['yshear'] = np.zeros(ny)
        geo_params['zshear'] = np.zeros(ny)

        # TODO: generalize this
        self.add_input('twist', val=geo_params['twist'])
        self.add_input('xshear', val=geo_params['xshear'])

        self.add_output('mesh', val=self.mesh)
        self.add_output('radius', val=np.zeros((ny - 1)))

        self.symmetry = surface['symmetry']

        # This flag determines whether or not changes in z (dihedral) add an
        # additional rotation matrix to modify the twist direction
        self.rotate_x = True


        if not fortran_flag:
            self.approx_partials('*', '*')

    def compute(self, inputs, outputs):
        mesh = self.mesh.copy()

        # Dirty hack for now; TODO: fix this
        for key in self.geo_params:
            try:
                if inputs[key].shape[0] > 1:
                    self.geo_params[key] = inputs[key]
                else:
                    self.geo_params[key] = inputs[key][0]
            except:
                pass

        # This line used to work in Clippy
        # self.geo_params.update(inputs)

        if fortran_flag:
            mesh = OAS_API.oas_api.manipulate_mesh(mesh,
            self.geo_params['taper'], self.geo_params['chord'],
            self.geo_params['sweep'], self.geo_params['xshear'],
            self.geo_params['span'], self.geo_params['yshear'],
            self.geo_params['dihedral'], self.geo_params['zshear'],
            self.geo_params['twist'], self.symmetry, self.rotate_x)

        else:
            taper(mesh, self.geo_params['taper'], self.symmetry)
            scale_x(mesh, self.geo_params['chord'])
            sweep(mesh, self.geo_params['sweep'], self.symmetry)
            shear_x(mesh, self.geo_params['xshear'])
            stretch(mesh, self.geo_params['span'], self.symmetry)
            shear_y(mesh, self.geo_params['yshear'])
            dihedral(mesh, self.geo_params['dihedral'], self.symmetry)
            shear_z(mesh, self.geo_params['zshear'])
            rotate(mesh, self.geo_params['twist'], self.symmetry, self.rotate_x)

        outputs['mesh'] = mesh

        outputs['radius'] = radii(mesh, self.metadata['surface']['t_over_c'])
        # outputs['radius'] = np.array([ 0.17806111,  0.20682864,  0.23559643,  0.26436396,  0.29313175,  0.32189928,
        #   0.35066707,  0.37936881,  0.4081366,   0.44796837,  0.50773076,  0.57649212,
        #   0.64529818,  0.71405547,  0.78276348])

    if fortran_flag:
        if 0:
            def compute_jacvec_product(
                    self, inputs, outputs, d_inputs, d_outputs, mode):

                mesh = self.mesh.copy()

                # We actually use the values in self.geo_params to modify the mesh,
                # but we update self.geo_params using the OpenMDAO params here.
                # This makes the geometry manipulation process work for any combination
                # of design variables without having special logic.
                # self.geo_params.update(inputs)

                # Dirty hack for now; TODO: fix this
                for key in self.geo_params:
                    try:
                        if inputs[key].shape[0] > 1:
                            self.geo_params[key] = inputs[key]
                        else:
                            self.geo_params[key] = inputs[key][0]
                    except:
                        pass

                if mode == 'fwd':

                    # We don't know which parameters will be used for a given case
                    # so we must check
                    if 'sweep' in d_inputs:
                        sweepd = d_inputs['sweep']
                    else:
                        sweepd = 0.
                    if 'twist' in d_inputs:
                        twistd = d_inputs['twist']
                    else:
                        twistd = np.zeros(self.geo_params['twist'].shape)
                    if 'chord' in d_inputs:
                        chordd = d_inputs['chord']
                    else:
                        chordd = np.zeros(self.geo_params['chord'].shape)
                    if 'dihedral' in d_inputs:
                        dihedrald = d_inputs['dihedral']
                    else:
                        dihedrald = 0.
                    if 'taper' in d_inputs:
                        taperd = d_inputs['taper']
                    else:
                        taperd = 0.
                    if 'xshear' in dparams:
                        xsheard = dparams['xshear']
                    else:
                        xsheard = np.zeros(self.geo_params['xshear'].shape)
                    if 'yshear' in dparams:
                        ysheard = dparams['yshear']
                    else:
                        ysheard = np.zeros(self.geo_params['yshear'].shape)
                    if 'zshear' in dparams:
                        zsheard = dparams['zshear']
                    else:
                        zsheard = np.zeros(self.geo_params['zshear'].shape)
                    if 'span' in dparams:
                        spand = dparams['span']
                    else:
                        spand = 0.

                    mesh, d_outputs['mesh'] = OAS_API.oas_api.manipulate_mesh_d(mesh,
                    self.geo_params['taper'], taperd, self.geo_params['chord'], chordd,
                    self.geo_params['sweep'], sweepd, self.geo_params['xshear'], xsheard,
                    self.geo_params['span'], spand, self.geo_params['yshear'], ysheard,
                    self.geo_params['dihedral'], dihedrald, self.geo_params['zshear'], zsheard,
                    self.geo_params['twist'], twistd, self.symmetry, self.rotate_x)

                if mode == 'rev':
                    taperb, chordb, sweepb, xshearb, spanb, yshearb, dihedralb, zshearb, twistb, mesh = \
                    OAS_API.oas_api.manipulate_mesh_b(mesh,
                    self.geo_params['taper'], self.geo_params['chord'],
                    self.geo_params['sweep'], self.geo_params['xshear'],
                    self.geo_params['span'], self.geo_params['yshear'],
                    self.geo_params['dihedral'], self.geo_params['zshear'],
                    self.geo_params['twist'], self.symmetry, self.rotate_x, dresids['mesh'])

                    if 'sweep' in d_inputs:
                        d_inputs['sweep'] += sweepb
                    if 'twist' in d_inputs:
                        d_inputs['twist'] += twistb
                    if 'chord' in d_inputs:
                        d_inputs['chord'] += chordb
                    if 'dihedral' in d_inputs:
                        d_inputs['dihedral'] += dihedralb
                    if 'taper' in d_inputs:
                        d_inputs['taper'] += taperb
                    if 'xshear' in d_inputs:
                        d_inputs['xshear'] += xshearb
                    if 'yshear' in dparams:
                        dparams['yshear'] = yshearb
                    if 'zshear' in d_inputs:
                        d_inputs['zshear'] += zshearb
                    if 'span' in d_inputs:
                        d_inputs['span'] += spanb

        else:
            def compute_partials(self, inputs, outputs, partials):

                # We actually use the values in self.geo_params to modify the mesh,
                # but we update self.geo_params using the OpenMDAO params here.
                # This makes the geometry manipulation process work for any combination
                # of design variables without having special logic.
                # self.geo_params.update(inputs)

                # Dirty hack for now; TODO: fix this
                for key in self.geo_params:
                    try:
                        if inputs[key].shape[0] > 1:
                            self.geo_params[key] = inputs[key]
                        else:
                            self.geo_params[key] = inputs[key][0]
                    except:
                        pass

                mesh = self.mesh.copy()

                for param in inputs:

                    d_inputs = {}
                    d_inputs[param] = self.geo_params[param].copy()

                    if isinstance(d_inputs[param], np.ndarray):
                        for j, val in enumerate(d_inputs[param].flatten()):
                            d_inputs[param][:] = 0.
                            d_inputs[param][j] = 1.

                            # We don't know which parameters will be used for a given case
                            # so we must check
                            if 'sweep' in d_inputs:
                                sweepd = d_inputs['sweep']
                            else:
                                sweepd = 0.
                            if 'twist' in d_inputs:
                                twistd = d_inputs['twist']
                            else:
                                twistd = np.zeros(self.geo_params['twist'].shape)
                            if 'chord' in d_inputs:
                                chordd = d_inputs['chord']
                            else:
                                chordd = np.zeros(self.geo_params['chord'].shape)
                            if 'dihedral' in d_inputs:
                                dihedrald = d_inputs['dihedral']
                            else:
                                dihedrald = 0.
                            if 'taper' in d_inputs:
                                taperd = d_inputs['taper']
                            else:
                                taperd = 0.
                            if 'xshear' in d_inputs:
                                xsheard = d_inputs['xshear']
                            else:
                                xsheard = np.zeros(self.geo_params['xshear'].shape)
                            if 'yxshear' in d_inputs:
                                ysheard = d_inputs['yshear']
                            else:
                                ysheard = np.zeros(self.geo_params['yshear'].shape)
                            if 'zshear' in d_inputs:
                                zsheard = d_inputs['zshear']
                            else:
                                zsheard = np.zeros(self.geo_params['zshear'].shape)
                            if 'span' in d_inputs:
                                spand = d_inputs['span']
                            else:
                                spand = 0.

                            _, mesh_d = OAS_API.oas_api.manipulate_mesh_d(mesh,
                            self.geo_params['taper'], taperd, self.geo_params['chord'], chordd,
                            self.geo_params['sweep'], sweepd, self.geo_params['xshear'], xsheard,
                            self.geo_params['span'], spand, self.geo_params['yshear'], ysheard,
                            self.geo_params['dihedral'], dihedrald, self.geo_params['zshear'], zsheard,
                            self.geo_params['twist'], twistd, self.symmetry, self.rotate_x)

                            partials['mesh', param][:, j] = mesh_d.flatten()

                    else:

                        d_inputs[param] = 1.

                        # We don't know which parameters will be used for a given case
                        # so we must check
                        if 'sweep' in d_inputs:
                            sweepd = d_inputs['sweep']
                        else:
                            sweepd = 0.
                        if 'twist' in d_inputs:
                            twistd = d_inputs['twist']
                        else:
                            twistd = np.zeros(self.geo_params['twist'].shape)
                        if 'chord' in d_inputs:
                            chordd = d_inputs['chord']
                        else:
                            chordd = np.zeros(self.geo_params['chord'].shape)
                        if 'dihedral' in d_inputs:
                            dihedrald = d_inputs['dihedral']
                        else:
                            dihedrald = 0.
                        if 'taper' in d_inputs:
                            taperd = d_inputs['taper']
                        else:
                            taperd = 0.
                        if 'xshear' in d_inputs:
                            xsheard = d_inputs['xshear']
                        else:
                            xsheard = np.zeros(self.geo_params['xshear'].shape)
                        if 'yshear' in d_inputs:
                            ysheard = d_inputs['yshear']
                        else:
                            ysheard = np.zeros(self.geo_params['yshear'].shape)
                        if 'zshear' in d_inputs:
                            zsheard = d_inputs['zshear']
                        else:
                            zsheard = np.zeros(self.geo_params['zshear'].shape)
                        if 'span' in d_inputs:
                            spand = d_inputs['span']
                        else:
                            spand = 0.

                        _, mesh_d = OAS_API.oas_api.manipulate_mesh_d(mesh,
                        self.geo_params['taper'], taperd, self.geo_params['chord'], chordd,
                        self.geo_params['sweep'], sweepd, self.geo_params['xshear'], xsheard,
                        self.geo_params['span'], spand, self.geo_params['yshear'], ysheard,
                        self.geo_params['dihedral'], dihedrald, self.geo_params['zshear'], zsheard,
                        self.geo_params['twist'], twistd, self.symmetry, self.rotate_x)

                        partials['mesh', param] = mesh_d.flatten()