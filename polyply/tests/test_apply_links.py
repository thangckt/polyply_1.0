# Copyright 2020 University of Groningen
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Test that force field files are properly read.
"""
# TODO
# linting and more unit tests

import textwrap
import pytest
import networkx as nx
import vermouth.forcefield
import vermouth.ffinput
from vermouth.molecule import Interaction
import polyply.src.meta_molecule
import polyply.src.map_to_molecule
import polyply.src.polyply_parser
import polyply.src.apply_links
from polyply.src.meta_molecule import (MetaMolecule, Monomer)
from polyply.src.apply_links import MatchError


class TestApplyLinks:
    @staticmethod
    @pytest.mark.parametrize('edges, orders, node, result', (
        # all ids and within graph
        ([(0, 1), (1, 2)],
         [0, 0, 1, 1],
         1,
         [[1, 1, 2, 2]]),
        # all ids but one not in grpah
        ([(0, 1), (1, 2)],
         [0, 1, 2, 3],
         0,
         [[0, 1, 2, 3]]),
        # some basic incl. '>'
        ([(0, 1), (1, 2)],
         [0, '>', '>'],
         0,
         [[0, 1, 1], [0, 2, 2]]),
        # some basic incl. '<'
        ([(0, 1), (1, 2)],
         [0, '<', '<'],
         2,
         [[2, 1, 1], [2, 0, 0]]),
        # some basic incl. '<' but going negative
        ([(0, 1), (1, 2)],
         [0, '<', '<'],
         0,
         []),
        # same as above but with explicit order int
        ([(0, 1), (1, 2)],
         [0, -1, -1],
         0,
         [[0, -1, -1]]),
        # simple branched case
        ([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)],
         [1, 0, 2],
         0,
         [[1, 0, 2]]),
        # more complex branched case
        # note that filtering is done later based on sub-graph
        ([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)],
         [1, 0, '>'],
         0,
         [[1, 0, 1], [1, 0, 2], [1, 0, 3], [1, 0, 4], [1, 0, 5], [1, 0, 6]]),
        # linear and some ids some '>'
        ([(0, 1), (1, 2)],
         [0, '>', '>>'],
         0,
         [[0, 1, 2]]),
        ([(0, 1), (1, 2), (2, 3), (3, 4)],
         [0, '<', '>'],
         2,
         [[2, 1, 3], [2, 1, 4], [2, 0, 3],
          [2, 0, 4]]),
    ))
    def test_orders_to_paths(edges, orders, node, result):
        graph = nx.Graph()
        graph.add_edges_from(edges)
        paths = polyply.src.apply_links._orders_to_paths(graph, orders, node)
        assert len(result) == len(paths)
        for ref_path in result:
            assert ref_path in paths

    @staticmethod
    def test_orders_to_paths_error():
        graph = nx.Graph()
        graph.add_edges_from([(0, 1), (1, 2)])
        with pytest.raises(IOError):
            polyply.src.apply_links._orders_to_paths(graph, [1, '*'], 0)

    @staticmethod
    @pytest.mark.parametrize('edges, orders, node, ref_edges', (
        # all ids and within graph
        ([(0, 1), (1, 2)],
         [0, 0, 1, 1],
         1,
         [[(1, 2)]]),
        # same nodes but split in order sequence
        ([(0, 1), (1, 2)],
         [0, 1, 1, 0],
         1,
         [[(1, 2)]]),
        # all ids but one not in grpah
        ([(0, 1), (1, 2)],
         [0, 1, 2, 3],
         0,
         [[(0, 1), (1, 2), (2, 3)]]),
        # linear and some ids some '>'
        ([(0, 1), (1, 2)],
         [0, '>', '>>'],
         0,
         [[(0, 1), (1, 2)], [(0, 2)]])
    ))
    def test_gen_link_fragments(edges, orders, node, ref_edges):
        """
        Test if the order paths are correctly converted to graphs.
        All this function really does besides calling order to
        paths as tested before is to make a graph skipping nodes
        which are the same.
        """
        graph = nx.Graph()
        graph.add_edges_from(edges)
        result_graph, _ = polyply.src.apply_links.gen_link_fragments(graph, orders, node)
        for graph in result_graph:
            assert list(graph.edges) in ref_edges

    @staticmethod
    @pytest.mark.parametrize('lines, edge_ref_ids', (
        ("""
        [ moleculetype ]
        ; name nexcl.
        PEO         1
        ;
        [ atoms ]
        1  SN1a    1   PEO   CO1  1   0.000  45
        [ link ]
        resname "PEO"
        [ bonds ]
        CO1 +CO1 params
        """,
         [[[1, 2], [2, 3]], [[2, 3], [3, 4]],
          [[3, 4], [4, 5]],
          [[4, 5]]]),
        ("""[ moleculetype ]
        ; name nexcl.
        PEO         1
        ;
        [ atoms ]
        1  SN1a    1   PEO   CO1  1   0.000  45
        [ link ]
        resname "PEO"
        [ bonds ]
        -CO1 CO1 params
        """,
         [[[1, 2]],
          [[1, 2], [2, 3]],
          [[2, 3], [3, 4]],
          [[3, 4], [4, 5]]]),
        ("""[ moleculetype ]
        ; name nexcl.
        PEO         1
        ;
        [ atoms ]
        1  SN1a    1   PEO   CO1  1   0.000  45
        [ link ]
        resname "PEO"
        [ angles ]
        CO1 +CO1 ++CO1
        """,
         [[[1, 2, 3],
           [2, 3, 4]],
          [[2, 3, 4],
           [3, 4, 5]],
          [[3, 4, 5]],
          []]),
        ("""[ moleculetype ]
        ; name nexcl.
        PEO         1
        ;
        [ atoms ]
        1  SN1a    1   PEO   CO1  1   0.000  45
        [ link ]
        resname "PEO"
        [ angles ]
        --CO1 -CO1 CO1
        """,
         [[],
          [[1, 2, 3]],
          [[1, 2, 3],
           [2, 3, 4]],
          [[2, 3, 4],
           [3, 4, 5]]]),
#       ("""[ moleculetype ]
#       ; name nexcl.
#       PEO         1
#       ;
#       [ atoms ]
#       1  SN1a    1   PEO   CO1  1   0.000  45
#       [ link ]
#       resname "PEO"
#       [ dihedrals ]
#       CO1 +CO1 >CO1 >>CO1
#       """,
#        [[1, 2, 2, 3], [1, 2, 3, 4], [2, 3, 3, 4],
#         [2, 3, 4, 5], [3, 4, 4, 5]])
    ))
    def test_get_links(lines, edge_ref_ids):
        lines = textwrap.dedent(lines).splitlines()
        force_field = vermouth.forcefield.ForceField(name='test_ff')
        vermouth.ffinput.read_ff(lines, force_field)
        meta_mol = MetaMolecule.from_monomer_seq_linear(force_field,
                                                        [Monomer(resname="PEO", n_blocks=5)],
                                                        "test")
        polyply.src.map_to_molecule.MapToMolecule().run_molecule(meta_mol)

        for edge, ref_ids in zip(meta_mol.edges, edge_ref_ids):
            print(edge)
            resids = []
            _, ids = polyply.src.apply_links._get_links(meta_mol, edge)
            resids += ids
            print(resids)
            assert len(resids) == len(ref_ids)
            for resid in ids:
                assert resid in ref_ids

#   @staticmethod
#   @pytest.mark.parametrize('links, interactions, edges, idx, inttype, atypes',
#        (("""
#        [ link ]
#        [ bonds ]
#        BB +BB  1  0.350  1250
#        """,
#        [vermouth.molecule.Interaction(atoms=(0, 1),
#                                       parameters=['1', '0.350', '1250'],
#                                       meta={})],
#        1,
#        [1, 2],
#        'bonds',
#        {0: 'SP2', 1: 'SP2', 2: 'SP2', 3: 'SC2'}),
#        ("""
#        [ link ]
#        [ bonds ]
#        BB   SC1   1  0.350  1250
#        """,
#        [vermouth.molecule.Interaction(atoms=(2, 3),
#                                       parameters=['1', '0.350', '1250'],
#                                       meta={})],
#        1,
#        [3, 3],
#        'bonds',
#        {0: 'SP2', 1: 'SP2', 2: 'SP2', 3:'SC2'}),
#        ("""
#        [ link ]
#        [ bonds ]
#        BB   -BB  1  0.350  1250
#        """,
#        [vermouth.molecule.Interaction(atoms=(1, 2),
#                                       parameters=['1', '0.350', '1250'],
#                                       meta={})],
#        1,
#        [2, 3],
#        'bonds',
#        {0: 'SP2', 1: 'SP2', 2: 'SP2', 3:'SC2'}),
#        ("""
#        [ link ]
#        [ atoms ]
#        BB  {"replace": {"atype": "P5"}}
#        [ bonds ]
#        BB   SC1   1  0.350  1250
#        """,
#        [vermouth.molecule.Interaction(atoms=(2, 3),
#                                       parameters=['1', '0.350', '1250'],
#                                       meta={})],
#        1,
#        [3, 3],
#        'bonds',
#        {0: 'SP2', 1: 'SP2', 2: 'P5', 3: 'SC2'}),
#        ("""
#        [ link ]
#        [ angles ]
#        BB  +BB  +SC1  1  125  250
#        """,
#       [vermouth.molecule.Interaction(atoms=(1, 2, 3),
#                                      parameters=['1', '125', '250'],
#                                      meta={})],
#       2,
#       [2, 3],
#       'angles',
#       {0: 'SP2', 1: 'SP2', 2: 'SP2', 3: 'SC2'})
#       ))
#   def test_add_interaction_and_edge(links, interactions, edges, idx, inttype, atypes):
#       lines = """
#       [ moleculetype ]
#       GLY  1
#       [ atoms ]
#       ;id  type resnr residu atom cgnr   charge
#        1   SP2   1     GLY    BB     1      0
#       [ moleculetype ]
#       ALA  1
#       [ atoms ]
#       ;id  type resnr residu atom cgnr   charge
#        1   SP2   1     ALA    BB     1      0
#        2   SC2   1     ALA    SC1     1      0
#       """
#       lines = lines + links
#       lines = textwrap.dedent(lines).splitlines()
#       force_field = vermouth.forcefield.ForceField(name='test_ff')
#       vermouth.ffinput.read_ff(lines, force_field)

#       new_mol = force_field.blocks['GLY'].to_molecule()
#       new_mol.merge_molecule(force_field.blocks['GLY'])
#       new_mol.merge_molecule(force_field.blocks['ALA'])

#       polyply.src.apply_links.apply_link_between_residues(new_mol,
#                                                           force_field.links[0],
#                                                           idx)
#       assert new_mol.interactions[inttype] == interactions
#       assert len(new_mol.edges) == edges
#       assert nx.get_node_attributes(new_mol, "atype") == atypes

#   @staticmethod
#   @pytest.mark.parametrize('links, idx',(
#      (  # no match considering the order parameter
#                                    """
#        [ link ]
#        [ bonds ]
#        BB   +BB  1  0.350  1250""",
#        [1, 4],
#      ),
#      (  # no match due to incorrect atom name
#                                    """
#        [ link ]
#        [ bonds ]
#        BB   SC5   1  0.350  1250
#        """,
#       [3, 3])))
#   def test_link_failure(links, idx):
#       lines = """
#       [ moleculetype ]
#       GLY  1
#       [ atoms ]
#       ;id  type resnr residu atom cgnr   charge
#        1   SP2   1     GLY    BB     1      0
#       [ moleculetype ]
#       ALA  1
#       [ atoms ]
#       ;id  type resnr residu atom cgnr   charge
#        1   SP2   1     ALA    BB     1      0
#        2   SC2   1     ALA    SC1    1      0
#       """
#       lines = lines + links
#       lines = textwrap.dedent(lines).splitlines()
#       force_field = vermouth.forcefield.ForceField(name='test_ff')
#       vermouth.ffinput.read_ff(lines, force_field)

#       new_mol = force_field.blocks['GLY'].to_molecule()
#       new_mol.merge_molecule(force_field.blocks['GLY'])
#       new_mol.merge_molecule(force_field.blocks['ALA'])

#       with pytest.raises(MatchError):
#           polyply.src.apply_links.apply_link_between_residues(
#               new_mol, force_field.links[0], idx)

    @staticmethod
    @pytest.mark.parametrize('links, interactions, edges, inttype',(
       ("""
       [ link ]
       [ molmeta ]
       by_atom_ID true
       [ bonds ]
       1   2  1  0.350  1250
       """,
       [vermouth.molecule.Interaction(atoms=(0, 1),
                                      parameters=['1', '0.350', '1250'],
                                      meta={})],
       1,
       'bonds'
       ),
       ("""
       [ link ]
       [ molmeta ]
       by_atom_ID true
       [ angles ]
       2  3  4  1  125  250
       """,
       [vermouth.molecule.Interaction(atoms=(1, 2, 3),
                                      parameters=['1', '125', '250'],
                                      meta={})],
       2,
       'angles')
       ))
    def test_add_explicit_link(links, interactions, edges, inttype):
        lines = """
        [ moleculetype ]
        GLY  1
        [ atoms ]
        ;id  type resnr residu atom cgnr   charge
         1   SP2   1     GLY    BB     1      0
        [ moleculetype ]
        ALA  1
        [ atoms ]
        ;id  type resnr residu atom cgnr   charge
         1   SP2   1     ALA    BB     1      0
         2   SC2   1     ALA    SC1     1      0
        """
        lines = lines + links
        lines = textwrap.dedent(lines).splitlines()
        force_field = vermouth.forcefield.ForceField(name='test_ff')
        vermouth.ffinput.read_ff(lines, force_field)

        new_mol = force_field.blocks['GLY'].to_molecule()
        new_mol.merge_molecule(force_field.blocks['GLY'])
        new_mol.merge_molecule(force_field.blocks['ALA'])

        polyply.src.apply_links.apply_explicit_link(
            new_mol, force_field.links[0])
        assert new_mol.interactions[inttype] == interactions
        assert len(new_mol.edges) == edges

    @staticmethod
    @pytest.mark.parametrize('links, error_type',
                             (("""
         [ link ]
         [ molmeta ]
         by_atom_ID true
         [ bonds ]
         BB  +BB  1  0.350  1250
         """,
                               ValueError
                               ),
                              ("""
         [ link ]
         [ molmeta ]
         by_atom_ID true
         [ angles ]
         1   8  1  125  250
         """,
                               IOError)
                              ))
    def test_explicit_link_failure(links, error_type):
        lines = """
        [ moleculetype ]
        GLY  1
        [ atoms ]
        ;id  type resnr residu atom cgnr   charge
         1   SP2   1     GLY    BB     1      0
        [ moleculetype ]
        ALA  1
        [ atoms ]
        ;id  type resnr residu atom cgnr   charge
         1   SP2   1     ALA    BB     1      0
         2   SC2   1     ALA    SC1    1      0
        """
        lines = lines + links
        lines = textwrap.dedent(lines).splitlines()
        force_field = vermouth.forcefield.ForceField(name='test_ff')
        vermouth.ffinput.read_ff(lines, force_field)

        new_mol = force_field.blocks['GLY'].to_molecule()
        new_mol.merge_molecule(force_field.blocks['GLY'])
        new_mol.merge_molecule(force_field.blocks['ALA'])

        with pytest.raises(error_type):
            polyply.src.apply_links.apply_explicit_link(
                new_mol, force_field.links[0])
    @staticmethod
    def test_expand_exclusions():
        mol = vermouth.Molecule()
        mol.nrexcl = 1
        mol.add_edges_from([(0, 1), (1, 2), (2, 3), (2, 4)])
        nx.set_node_attributes(mol, {0:1, 1:2, 2:2, 3:2, 4:2}, "exclude")
        mol = polyply.src.apply_links.expand_excl(mol)
        ref_excl = [frozenset([0, 1]),
                    frozenset([1, 2]),
                    frozenset([2, 0]),
                    frozenset([2, 3]),
                    frozenset([2, 4]),
                    frozenset([3, 4]),
                    frozenset([3, 1]),
                    frozenset([4, 1])]
        print(mol.interactions["exclusions"])
        assert len(ref_excl) == len(mol.interactions["exclusions"])
        for excl in mol.interactions["exclusions"]:
            assert frozenset(excl.atoms) in ref_excl



