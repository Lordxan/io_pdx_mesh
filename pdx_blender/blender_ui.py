"""
    Paradox asset files, Blender import/export interface.

    author : ross-g
"""

import os
import json
import inspect
import importlib
from collections import OrderedDict
from textwrap import wrap

import bpy
from bpy.types import Operator, Panel, UIList
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper

from .. import bl_info, IO_PDX_LOG, IO_PDX_SETTINGS
from ..pdx_data import PDXData
from ..updater import github

try:
    from . import blender_import_export
    importlib.reload(blender_import_export)
    from .blender_import_export import (
        create_shader,
        export_animfile,
        export_meshfile,
        get_mesh_index,
        import_animfile,
        import_meshfile,
        list_scene_pdx_meshes,
        PDX_SHADER,
        set_ignore_joints,
        set_local_axis_display,
    )
except Exception as err:
    IO_PDX_LOG.error(err)
    raise


""" ====================================================================================================================
    Variables and Helper functions.
========================================================================================================================
"""


_script_dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
settings_file = os.path.join(os.path.split(_script_dir)[0], 'clausewitz.json')

engine_list = ()


def load_settings():
    global settings_file
    with open(settings_file, 'rt') as f:
        try:
            settings = json.load(f, object_pairs_hook=OrderedDict)
            return settings
        except Exception as err:
            IO_PDX_LOG.info("CRITICAL ERROR!")
            IO_PDX_LOG.error(err)
            return {}


def get_engine_list(self, context):
    global engine_list

    settings = load_settings()  # settings from json
    engine_list = ((engine, engine, engine) for engine in settings.keys())

    return engine_list


def get_material_list(self, context):
    sel_engine = context.scene.io_pdx_settings.setup_engine

    settings = load_settings()  # settings from json
    material_list = [(material, material, material) for material in settings[sel_engine]['material']]
    material_list.insert(0, ('__NONE__', '', ''))

    return material_list


def get_scene_material_list(self, context):
    material_list = [(mat.name, mat.name, mat.name) for mat in bpy.data.materials if mat.get(PDX_SHADER, None)]

    return material_list


def set_animation_fps(self, context):
    context.scene.render.fps = context.scene.io_pdx_settings.setup_fps


""" ====================================================================================================================
    Operator classes called by the tool UI.
========================================================================================================================
"""


class IOPDX_OT_popup_message(Operator):
    bl_idname = 'io_pdx_mesh.popup_message'
    bl_label = bl_info['name']
    bl_description = 'Popup Message'
    bl_options = {'REGISTER'}

    msg_text : StringProperty(
        default='NOT YET IMPLEMENTED!',
    )
    msg_icon : StringProperty(
        default='ERROR',  # 'QUESTION', 'CANCEL', 'INFO'
    )
    msg_width : IntProperty(
        default=300,
    )

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=self.msg_width)

    def draw(self, context):
        self.layout.operator_context = 'INVOKE_DEFAULT'

        # split text into multiple label rows if it's wider than the panel
        txt_lines = []
        for line in self.msg_text.splitlines():
            txt_lines.extend(wrap(line, self.msg_width / 6))
            txt_lines.append('')

        col = self.layout.column(align=True)
        col.label(text=txt_lines[0], icon=self.msg_icon)
        for line in txt_lines[1:]:
            if line:
                col.label(text=line)
            else:
                col.separator()

        col.label(text='')


class material_popup(object):
    bl_options = {'REGISTER'}

    mat_name : StringProperty(
        name='Name',
        default=''
    )
    mat_type : EnumProperty(
        name='Shader preset',
        items=get_material_list
    )
    use_custom : BoolProperty(
        name='custom Shader:',
        default=False,
    )
    custom_type : StringProperty(
        name='Shader',
        default=''
    )


class IOPDX_OT_material_create_popup(material_popup, Operator):
    bl_idname = 'io_pdx_mesh.material_create_popup'
    bl_description = bl_label = 'Create a PDX material'

    def check(self, context):
        return True

    def execute(self, context):
        mat_name = self.mat_name
        mat_type = self.mat_type
        if self.use_custom or mat_type == '__NONE__':
            mat_type = self.custom_type
        # create a mock PDXData object for convenience here to pass to the create_shader function
        mat_pdx = type(
            'Material',
            (PDXData, object),
            {'shader': [mat_type]}
        )

        create_shader(mat_pdx, mat_name, None, placeholder=True)
        return {'FINISHED'}

    def invoke(self, context, event):
        self.mat_name = ''
        self.mat_type = '__NONE__'
        self.use_custom = False
        self.custom_type = ''
        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context):
        box = self.layout.box()
        box.prop(self, 'mat_name')
        box.prop(self, 'mat_type')
        row = box.split(factor=0.33)
        row.prop(self, 'use_custom')
        if self.use_custom:
            row.prop(self, 'custom_type', text='')
        self.layout.separator()


class IOPDX_OT_material_edit_popup(material_popup, Operator):
    bl_idname = 'io_pdx_mesh.material_edit_popup'
    bl_description = bl_label = 'Edit a PDX material'

    def mat_select(self, context):
        mat = bpy.data.materials[self.scene_mats]

        curr_mat = context.scene.io_pdx_material
        curr_mat.mat_name = mat.name
        curr_mat.mat_type = mat[PDX_SHADER]

    scene_mats : EnumProperty(
        name='Selected material',
        items=get_scene_material_list,
        update=mat_select
    )

    def check(self, context):
        return True

    def execute(self, context):
        mat = bpy.data.materials[self.scene_mats]
        curr_mat = context.scene.io_pdx_material
        mat.name = curr_mat.mat_name
        mat[PDX_SHADER] = curr_mat.mat_type
        return {'FINISHED'}

    def invoke(self, context, event):
        pdx_scene_materials = get_scene_material_list(self, context)
        if pdx_scene_materials:
            if self.scene_mats in bpy.data.materials:
                self.mat_select(context)
                mat = bpy.data.materials[self.scene_mats]
                self.mat_name = mat.name
                self.custom_type = mat[PDX_SHADER]
                return context.window_manager.invoke_props_dialog(self, width=350)
            else:
                return {'CANCELLED'}
        else:
            bpy.ops.io_pdx_mesh.popup_message('INVOKE_DEFAULT', msg_text='NO PDX MATERIALS FOUND IN THE SCENE!')
            return {'CANCELLED'}

    def draw(self, context):
        curr_mat = context.scene.io_pdx_material

        self.layout.prop(self, 'scene_mats')
        self.layout.separator()

        box = self.layout.box()
        box.prop(curr_mat, 'mat_name')
        box.prop(curr_mat, 'mat_type')
        self.layout.separator()


class IOPDX_UL_mesh_index_list(UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'name', text='', emboss=False)


class IOPDX_OT_mesh_index_actions(Operator):
    bl_idname = "io_pdx_mesh.mesh_index_actions"
    bl_description = bl_label = "Mesh index list actions"
    bl_options = {'REGISTER'}

    action : EnumProperty(
        items=(('UP', "Up", ""), ('DOWN', "Down", ""))
    )

    @classmethod
    def poll(cls, context):
        return context.scene.io_pdx_group

    def move_index(self):
        list_index = bpy.context.scene.io_pdx_group.idx
        list_length = len(bpy.context.scene.io_pdx_group.coll) - 1

        new_index = list_index + (-1 if self.action == 'UP' else 1)
        bpy.context.scene.io_pdx_group.idx = max(0, min(new_index, list_length))

    def execute(self, context):
        collection = context.scene.io_pdx_group.coll
        index = context.scene.io_pdx_group.idx
        neighbor = index + (-1 if self.action == 'UP' else 1)
        collection.move(neighbor, index)
        self.move_index()

        return {'FINISHED'}


class IOPDX_OT_mesh_index_popup(Operator):
    bl_idname = 'io_pdx_mesh.mesh_index_popup'
    bl_description = bl_label = 'Set mesh index on PDX meshes'
    bl_options = {'REGISTER'}

    def check(self, context):
        return True

    def execute(self, context):
        for i, item in enumerate(context.scene.io_pdx_group.coll):
            item.ref.data['meshindex'] = i
        return {'FINISHED'}

    def invoke(self, context, event):
        obj_group = context.scene.io_pdx_group

        obj_group.coll.clear()
        pdx_scenemeshes = list_scene_pdx_meshes()
        pdx_scenemeshes.sort(key=lambda obj: get_mesh_index(obj.data))

        for obj in pdx_scenemeshes:
            item = obj_group.coll.add()
            item.name = obj.name
            item.ref = obj
        return context.window_manager.invoke_props_dialog(self, width=200)

    def draw(self, context):
        obj_group = context.scene.io_pdx_group
        row = self.layout.row()
        row.template_list('IOPDX_UL_mesh_index_list', '', obj_group, 'coll', obj_group, 'idx', rows=8)

        col = row.column(align=True)
        col.operator("io_pdx_mesh.mesh_index_actions", icon='TRIA_UP', text="").action = 'UP'
        col.operator("io_pdx_mesh.mesh_index_actions", icon='TRIA_DOWN', text="").action = 'DOWN'
        self.layout.separator()


class IOPDX_OT_import_mesh(Operator, ImportHelper):
    bl_idname = 'io_pdx_mesh.import_mesh'
    bl_description = bl_label = 'Import PDX mesh'
    bl_options = {'REGISTER', 'UNDO'}

    # ImportHelper mixin class uses these
    filename_ext = '.mesh'
    filter_glob : StringProperty(
        default='*.mesh',
        options={'HIDDEN'},
        maxlen=255,
    )
    filepath : StringProperty(
        name="Import file Path",
        maxlen=1024,
    )

    # list of operator properties
    chk_mesh : BoolProperty(
        name='Import mesh',
        description='Import mesh',
        default=True,
    )
    chk_skel : BoolProperty(
        name='Import skeleton',
        description='Import skeleton',
        default=True,
    )
    chk_locs : BoolProperty(
        name='Import locators',
        description='Import locators',
        default=True,
    )
    chk_bonespace : BoolProperty(
        name='Convert bone orientation - WARNING',
        description='Convert bone orientation - WARNING: this re-orients bones authored in Maya, but will BREAK ALL '
                    'EXISTING ANIMATIONS. Only use this option if you are going to re-animate the model.',
        default=False,
    )

    def draw(self, context):
        box = self.layout.box()
        box.label(text='Settings:', icon='IMPORT')
        box.prop(self, 'chk_mesh')
        box.prop(self, 'chk_skel')
        box.prop(self, 'chk_locs')
        # box.prop(self, 'chk_bonespace')  # TODO: works but overcomplicates things, disabled for now

    def execute(self, context):
        try:
            import_meshfile(
                self.filepath,
                imp_mesh=self.chk_mesh,
                imp_skel=self.chk_skel,
                imp_locs=self.chk_locs,
                bonespace=self.chk_bonespace
            )
            self.report({'INFO'}, '[io_pdx_mesh] Finsihed importing {}'.format(self.filepath))
            IO_PDX_SETTINGS.last_import_mesh = self.filepath

        except Exception as err:
            IO_PDX_LOG.warning("FAILED to import {0}".format(self.filepath))
            IO_PDX_LOG.error(err)
            self.report({'WARNING'}, 'Mesh import failed!')
            self.report({'ERROR'}, str(err))
            raise

        return {'FINISHED'}

    def invoke(self, context, event):
        self.filepath = IO_PDX_SETTINGS.last_import_mesh or ''
        context.window_manager.fileselect_add(self)

        return {'RUNNING_MODAL'}


class IOPDX_OT_import_anim(Operator, ImportHelper):
    bl_idname = 'io_pdx_mesh.import_anim'
    bl_description = bl_label = 'Import PDX animation'
    bl_options = {'REGISTER', 'UNDO'}

    # ImportHelper mixin class uses these
    filename_ext = '.anim'
    filter_glob : StringProperty(
        default='*.anim',
        options={'HIDDEN'},
        maxlen=255,
    )
    filepath : StringProperty(
        name="Import file Path",
        maxlen=1024,
    )

    # list of operator properties
    int_start : IntProperty(
        name='Start frame',
        description='Start frame',
        default=1,
    )

    def draw(self, context):
        box = self.layout.box()
        box.label(text='Settings:', icon='IMPORT')
        box.prop(self, 'int_start')

    def execute(self, context):
        try:
            import_animfile(
                self.filepath,
                timestart=self.int_start
            )
            self.report({'INFO'}, '[io_pdx_mesh] Finsihed importing {}'.format(self.filepath))
            IO_PDX_SETTINGS.last_import_anim = self.filepath

        except Exception as err:
            IO_PDX_LOG.warning("FAILED to import {0}".format(self.filepath))
            IO_PDX_LOG.error(err)
            self.report({'WARNING'}, 'Animation import failed!')
            self.report({'ERROR'}, str(err))
            raise

        return {'FINISHED'}

    def invoke(self, context, event):
        self.filepath = IO_PDX_SETTINGS.last_import_anim or ''
        context.window_manager.fileselect_add(self)

        return {'RUNNING_MODAL'}


class IOPDX_OT_export_mesh(Operator, ExportHelper):
    bl_idname = 'io_pdx_mesh.export_mesh'
    bl_description = bl_label = 'Export PDX mesh'
    bl_options = {'REGISTER', 'UNDO'}

    # ExportHelper mixin class uses these
    filename_ext = '.mesh'
    filter_glob : StringProperty(
        default='*.mesh',
        options={'HIDDEN'},
        maxlen=255,
    )
    filepath : StringProperty(
        name="Export file Path",
        maxlen=1024,
    )

    # list of operator properties
    chk_mesh : BoolProperty(
        name='Export mesh',
        description='Export mesh',
        default=True,
    )
    chk_skel : BoolProperty(
        name='Export skeleton',
        description='Export skeleton',
        default=True,
    )
    chk_locs : BoolProperty(
        name='Export locators',
        description='Export locators',
        default=True,
    )
    chk_merge : BoolProperty(
        name='Merge vertices',
        description='Merge vertices',
        default=True,
    )
    chk_selected : BoolProperty(
        name='Export selected only',
        description='Export selected only',
        default=False,
    )

    def draw(self, context):
        box = self.layout.box()
        box.label(text='Settings:', icon='EXPORT')
        box.prop(self, 'chk_mesh')
        box.prop(self, 'chk_skel')
        box.prop(self, 'chk_locs')
        box.prop(self, 'chk_merge')
        box.prop(self, 'chk_selected')

    def execute(self, context):
        try:
            export_meshfile(
                self.filepath,
                exp_mesh=self.chk_mesh,
                exp_skel=self.chk_skel,
                exp_locs=self.chk_locs,
                merge_verts=self.chk_merge,
                selected_only=self.chk_selected
            )
            self.report({'INFO'}, '[io_pdx_mesh] Finsihed exporting {}'.format(self.filepath))
            IO_PDX_SETTINGS.last_export_mesh = self.filepath

        except Exception as err:
            IO_PDX_LOG.warning("FAILED to export {0}".format(self.filepath))
            IO_PDX_LOG.error(err)
            self.report({'WARNING'}, 'Mesh export failed!')
            self.report({'ERROR'}, str(err))
            raise

        return {'FINISHED'}

    def invoke(self, context, event):
        self.filepath = IO_PDX_SETTINGS.last_export_mesh or ''
        context.window_manager.fileselect_add(self)

        return {'RUNNING_MODAL'}


class IOPDX_OT_export_anim(Operator, ExportHelper):
    bl_idname = 'io_pdx_mesh.export_anim'
    bl_description = bl_label = 'Export PDX animation'
    bl_options = {'REGISTER', 'UNDO'}

    # ExportHelper mixin class uses these
    filename_ext = '.anim'
    filter_glob : StringProperty(
        default='*.anim',
        options={'HIDDEN'},
        maxlen=255,
    )
    filepath : StringProperty(
        name="Export file Path",
        maxlen=1024,
    )

    # list of operator properties
    int_start : IntProperty(
        name='Start frame',
        description='Start frame',
        default=1,
    )
    int_end : IntProperty(
        name='End frame',
        description='End frame',
        default=100,
    )

    def draw(self, context):
        settings = context.scene.io_pdx_export

        box = self.layout.box()
        box.label(text='Settings:', icon='EXPORT')
        box.prop(settings, 'custom_range')
        col = box.column()
        col.enabled = settings.custom_range
        col.prop(self, 'int_start')
        col.prop(self, 'int_end')

    def execute(self, context):
        settings = context.scene.io_pdx_export

        try:
            if settings.custom_range:
                export_animfile(
                    self.filepath,
                    timestart=self.int_start,
                    timeend=self.int_end
                )
            else:
                export_animfile(
                    self.filepath,
                    timestart=context.scene.frame_start,
                    timeend=context.scene.frame_end
                )
            self.report({'INFO'}, '[io_pdx_mesh] Finsihed exporting {}'.format(self.filepath))
            IO_PDX_SETTINGS.last_export_anim = self.filepath

        except Exception as err:
            IO_PDX_LOG.warning("FAILED to export {0}".format(self.filepath))
            IO_PDX_LOG.error(err)
            self.report({'WARNING'}, 'Animation export failed!')
            self.report({'ERROR'}, str(err))
            raise

        return {'FINISHED'}

    def invoke(self, context, event):
        self.filepath = IO_PDX_SETTINGS.last_export_anim or ''
        context.window_manager.fileselect_add(self)

        return {'RUNNING_MODAL'}


class IOPDX_OT_show_axis(Operator):
    bl_idname = 'io_pdx_mesh.show_axis'
    bl_description = bl_label = 'Show / hide local axis'
    bl_options = {'REGISTER'}

    show : BoolProperty(
        default=True
    )
    data_type : EnumProperty(
        name='Data type',
        items=(
            ('EMPTY', 'Empty', 'Empty', 1),
            ('ARMATURE', 'Armature', 'Armature', 2)
        )
    )

    def execute(self, context):
        set_local_axis_display(self.show, self.data_type)
        return {'FINISHED'}


class IOPDX_OT_ignore_bone(Operator):
    bl_idname = 'io_pdx_mesh.ignore_bone'
    bl_description = bl_label = 'Ignore / Unignore selected bones'
    bl_options = {'REGISTER'}

    state : BoolProperty(
        default=False
    )

    def execute(self, context):
        set_ignore_joints(self.state)
        return {'FINISHED'}


""" ====================================================================================================================
    UI classes for the import/export tool.
========================================================================================================================
"""


class PDXUI(object):
    bl_category = 'PDX Blender Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'


class IOPDX_PT_PDXblender_file(PDXUI, Panel):
    # bl_idname = 'panel.io_pdx_mesh.file'
    bl_label = 'File'
    panel_order = 1

    def draw(self, context):
        self.layout.label(text='Import:', icon='IMPORT')
        row = self.layout.row(align=True)
        row.operator('io_pdx_mesh.import_mesh', icon='MESH_CUBE', text='Load mesh ...')
        row.operator('io_pdx_mesh.import_anim', icon='RENDER_ANIMATION', text='Load anim ...')

        self.layout.label(text='Export:', icon='EXPORT')
        row = self.layout.row(align=True)
        row.operator('io_pdx_mesh.export_mesh', icon='MESH_CUBE', text='Save mesh ...')
        row.operator('io_pdx_mesh.export_anim', icon='RENDER_ANIMATION', text='Save anim ...')


class IOPDX_PT_PDXblender_tools(PDXUI, Panel):
    # bl_idname = 'panel.io_pdx_mesh.tools'
    bl_label = 'Tools'
    panel_order = 2

    def draw(self, context):
        col = self.layout.column(align=True)

        col.label(text='PDX materials:')
        row = col.row(align=True)
        row.operator('io_pdx_mesh.material_create_popup', icon='MATERIAL', text='Create')
        row.operator('io_pdx_mesh.material_edit_popup', icon='SHADING_TEXTURE', text='Edit')
        col.separator()

        col.label(text='PDX bones:')
        row = col.row(align=True)
        op_ignore_bone = row.operator('io_pdx_mesh.ignore_bone', icon='GROUP_BONE', text='Ignore bones')
        op_ignore_bone.state = True
        op_unignore_bone = row.operator('io_pdx_mesh.ignore_bone', icon='BONE_DATA', text='Unignore bones')
        op_unignore_bone.state = False
        col.separator()

        # col.label(text='PDX animations:')
        # row = col.row(align=True)
        # row.operator('io_pdx_mesh.popup_message', icon='IPO_BEZIER', text='Create')
        # row.operator('io_pdx_mesh.popup_message', icon='NORMALIZE_FCURVES', text='Edit')
        # col.separator()

        col.label(text='PDX meshes:')
        row = col.row(align=True)
        row.operator('io_pdx_mesh.mesh_index_popup', icon='SORTALPHA', text='Set mesh order')


class IOPDX_PT_PDXblender_display(PDXUI, Panel):
    # bl_idname = 'panel.io_pdx_mesh.display'
    bl_label = 'Display'
    bl_options = {'DEFAULT_CLOSED'}
    panel_order = 3

    def draw(self, context):
        col = self.layout.column(align=True)

        col.label(text='Display local axes:')
        row = col.row(align=True)
        op_show_bone_axis = row.operator('io_pdx_mesh.show_axis', icon='OUTLINER_OB_ARMATURE', text='Show on bones')
        op_show_bone_axis.show = True
        op_show_bone_axis.data_type = 'ARMATURE'
        op_hide_bone_axis = row.operator('io_pdx_mesh.show_axis', icon='OUTLINER_DATA_ARMATURE', text='Hide on bones')
        op_hide_bone_axis.show = False
        op_hide_bone_axis.data_type = 'ARMATURE'
        row = col.row(align=True)
        op_show_loc_axis = row.operator('io_pdx_mesh.show_axis', icon='OUTLINER_OB_EMPTY', text='Show on empties')
        op_show_loc_axis.show = True
        op_show_loc_axis.data_type = 'EMPTY'
        op_hide_loc_axis = row.operator('io_pdx_mesh.show_axis', icon='OUTLINER_DATA_EMPTY', text='Hide on empties')
        op_hide_loc_axis.show = False
        op_hide_loc_axis.data_type = 'EMPTY'


class IOPDX_PT_PDXblender_setup(PDXUI, Panel):
    # bl_idname = 'panel.io_pdx_mesh.setup'
    bl_label = 'Setup'
    bl_options = {'DEFAULT_CLOSED'}
    panel_order = 4

    def draw(self, context):
        settings = context.scene.io_pdx_settings

        self.layout.prop(settings, 'setup_engine')
        row = self.layout.row(align=True)
        row.label(text='Animation:')
        row.prop(settings, 'setup_fps', text='FPS')


class IOPDX_PT_PDXblender_info(PDXUI, Panel):
    # bl_idname = 'panel.io_pdx_mesh.help'
    bl_label = 'Version'
    # bl_options = {'HIDE_HEADER'}
    panel_order = 5

    def draw(self, context):
        col = self.layout.column(align=True)

        col.label(text='current version: {}'.format(github.CURRENT_VERSION))
        if github.AT_LATEST is False:   # update info appears if we aren't at the latest tag version
            btn_txt = 'NEW UPDATE {}'.format(github.LATEST_VERSION)
            split = col.split(factor=0.7, align=True)
            split.operator('wm.url_open', icon='FUND', text=btn_txt).url = str(github.LATEST_URL)
            popup = split.operator('io_pdx_mesh.popup_message', icon='INFO', text='About')
            popup.msg_text = github.LATEST_NOTES
            popup.msg_icon = 'INFO'
            popup.msg_width = 450


class IOPDX_PT_PDXblender_help(PDXUI, Panel):
    # bl_idname = 'panel.io_pdx_mesh.help'
    bl_label = 'Help'
    bl_parent_id = "IOPDX_PT_PDXblender_info"
    bl_options = {'DEFAULT_CLOSED'}
    panel_order = 6

    def draw(self, context):
        col = self.layout.column(align=True)

        col.operator('wm.url_open', icon='QUESTION', text='Addon Wiki').url = bl_info['wiki_url']
        col.operator('wm.url_open', icon='QUESTION', text='Paradox forums').url = bl_info['forum_url']
        col.operator('wm.url_open', icon='QUESTION', text='Source code').url = bl_info['project_url']
