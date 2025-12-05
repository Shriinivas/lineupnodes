#
# This Blender add-on arranges nodes within node editor windows of geometry
# nodes, shader nodes and compositor nodes
#
# Copyright (C) 2022  Shrinivas Kulkarni
#
# License: GPL3 (https://github.com/Shriinivas/lineupnodes/blob/main/LICENSE)
#

import bpy
from bpy.types import PropertyGroup, Operator, Panel
from bpy.props import EnumProperty, IntProperty, BoolProperty

bl_info = {
    "name": "Line Up Nodes",
    "author": "Shrinivas Kulkarni",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "Shader/Geometry/Compositor Node Editor > Sidebar > Edit Tab",
    "description": "Line up nodes",
    "category": "Object",
}


class SrcLinkInfo:
    def __init__(self):
        self.linkCntMap = {}

        # For arrangeType MAX
        self.maxLinkCnt = 0
        self.maxLinkNode = 0

        # For arrangeType FIRST and LAST
        self.row = None
        self.column = None

    def addLinkCnt(self, destNode):
        if self.linkCntMap.get(destNode) is None:
            self.linkCntMap[destNode] = 0
        self.linkCntMap[destNode] += 1

        if self.linkCntMap[destNode] > self.maxLinkCnt:
            self.maxLinkCnt = self.linkCntMap[destNode]
            self.maxLinkNode = destNode

    def removeDestNode(self, destNode):
        if self.linkCntMap.get(destNode) is not None:
            return self.linkCntMap.pop(destNode)

    def getLinkNodeCnt(self):
        return len(self.linkCntMap)

    def __repr__(self):
        return (
            f"[[{self.maxLinkCnt}->{self.maxLinkNode.name}--"
            + str({k.name: self.linkCntMap[k] for k in self.linkCntMap})
            + "]]"
        )


def getActiveNodeTree(context):
    """Get the active/edited node tree based on the current UI type.
    
    Returns:
        tuple: (nodeTree, error, path) where path is the edit tree path
    """
    uitype = context.area.ui_type
    nodeTree = None
    
    if uitype == "ShaderNodeTree":
        obj = context.active_object
        if obj is None:
            return None, "No active object selected. Please select an object.", None
        if obj.active_material is None:
            return None, f"Object '{obj.name}' has no active material. Please add a material.", None
        nodeTree = obj.active_material.node_tree
        if nodeTree is None:
            return None, f"Material '{obj.active_material.name}' has no node tree. Please use nodes.", None
            
    elif uitype == "GeometryNodeTree":
        obj = context.active_object
        if obj is None:
            return None, "No active object selected. Please select an object.", None
        if obj.modifiers.active is None:
            return None, f"Object '{obj.name}' has no active modifier. Please add a Geometry Nodes modifier.", None
        if obj.modifiers.active.type != 'NODES':
            return None, f"Active modifier is not a Geometry Nodes modifier. Please select a Geometry Nodes modifier.", None
        nodeTree = obj.modifiers.active.node_group
        if nodeTree is None:
            return None, "Geometry Nodes modifier has no node group. Please assign a node group.", None
            
    elif uitype == "CompositorNodeTree":
        nodeTree = context.scene.node_tree
        if nodeTree is None:
            return None, "Compositor has no node tree. Please enable 'Use Nodes' in compositor.", None
    
    # Get the currently edited tree (for when inside a group)
    space = context.space_data
    if space and hasattr(space, 'edit_tree') and space.edit_tree:
        # User is inside a node group, use the edited tree
        edit_tree = space.edit_tree
        # Get the path to know which node we're editing
        path = list(space.path) if hasattr(space, 'path') else []
        return edit_tree, None, path
    
    return nodeTree, None, []


def processNodes(
    srcNodeMap, nodeGraph, nodeTree, destNode, srcNodes, depth, arrangeType, maxColNodes, filteredLinks, maxDepth=100
):
    # T002: Prevent infinite recursion with depth limit
    if depth >= maxDepth:
        print(f"Warning: Maximum graph depth ({maxDepth}) reached. Possible cycle detected or very deep node tree.")
        return
    
    if len(nodeGraph) == depth:
        nodeGraph.append([])
    nodeColumn = nodeGraph[depth]
    for node in srcNodes:
        if maxColNodes > 0:
            while maxColNodes == len(nodeGraph[depth]) and len(nodeGraph) > depth:
                depth += 1
        # depth 0 means pure dest nodes, so process
        if depth == 0:
            pass
        else:
            srcLinkInfo = srcNodeMap.get(node)
            if srcLinkInfo is None:  # Already processed
                continue
            elif arrangeType == "MAX":
                if srcLinkInfo.maxLinkNode == destNode:
                    srcNodeMap.pop(node)
                else:
                    continue
            else:
                srcLinkInfo.removeDestNode(destNode)
                # srcLinkInfo.column is initialized with None so None means
                # the first time
                colNo = srcLinkInfo.column
                if (
                    colNo is None
                    or (colNo < depth and arrangeType == "LAST")
                    or (colNo > depth and arrangeType == "FIRST")
                ):
                    # If the node is already there in nodeGraph,
                    # remove it by setting its position element to None
                    if srcLinkInfo.column is not None:
                        prevCol = srcLinkInfo.column
                        prevRow = srcLinkInfo.row
                        nodeGraph[prevCol][prevRow] = None
                    srcLinkInfo.column = depth
                    srcLinkInfo.row = len(nodeGraph[depth])
                else:
                    continue

        # T003 Fix: Removed duplicate append - line 103-104 already creates column
        nodeGraph[depth].append(node)
        srcNodes = {k.from_node for k in filteredLinks if k.to_node == node}
        processNodes(
            srcNodeMap,
            nodeGraph,
            nodeTree,
            node,
            srcNodes,
            depth + 1,
            arrangeType,
            maxColNodes,
            filteredLinks,
        )


def displayNodes(nodeGraph, vAlign, xOffset, yOffset):
    origin = [0, 0]
    currLoc = origin[:]
    groupNodes = set()
    for origCol in nodeGraph:
        col = []  # Remove all None nodes to make logic easier
        for node in origCol:
            if node is not None:
                col.append(node)
        if len(col) == 0:
            continue
        if vAlign in {"MIDDLE", "BOTTOM"}:
            colHeight = sum(
                [n.dimensions[1] for n in col if n is not None]
            ) + yOffset * (len(col) - 1)
            currLoc[1] = (colHeight / 2) if vAlign == "MIDDLE" else colHeight
        maxWidth = max([n.dimensions[0] for n in col if n is not None])
        for i, node in enumerate(col):
            loc = [currLoc[0] - (maxWidth + node.dimensions[0]) / 2, currLoc[1]]
            if i > 0:
                prevNode = col[i - 1]
                loc[1] = prevNode.location[1] - prevNode.dimensions[1] - yOffset
            node.location = loc
            if node.type == "GROUP":
                groupNodes.add(node)
        currLoc[0] -= maxWidth + xOffset
        currLoc[1] = 0
    return groupNodes


def getOverride():
    """Get context override for node editor operations.
    
    Returns:
        dict or None: Context override dictionary, or None if NODE_EDITOR not found.
    """
    win = bpy.context.window
    screen = win.screen
    # T004: Validate NODE_EDITOR area exists
    node_editor_areas = [a for a in screen.areas if a.type == "NODE_EDITOR"]
    if not node_editor_areas:
        print("Warning: No NODE_EDITOR area found in current layout.")
        return None
    area = node_editor_areas[0]
    region = [region for region in area.regions if region.type == "WINDOW"]
    if not region:
        print("Warning: No WINDOW region found in NODE_EDITOR area.")
        return None
    return {"window": win, "screen": screen, "area": area, "region": region[0]}


def createSrcNodeMap(nodeTree):
    srcNodeMap = {}
    links = nodeTree.links
    for k in links:
        srcLinkInfo = srcNodeMap.get(k.from_node)
        if srcLinkInfo is None:
            srcLinkInfo = SrcLinkInfo()
            srcNodeMap[k.from_node] = srcLinkInfo
        srcLinkInfo.addLinkCnt(k.to_node)
    return srcNodeMap


def displayTree(
    nodeTree, vAlign, xOffset, yOffset, includeGroup, arrangeType, maxColNodes, applyToSelection=False, path=None
):
    # Early exit if node tree is empty (T005)
    if len(nodeTree.nodes) == 0:
        return "No nodes to arrange in the node tree."
    
    # T010: Filter by selection if requested
    all_nodes = list(nodeTree.nodes)
    if applyToSelection:
        selected_nodes = [n for n in all_nodes if n.select]
        print(f"DEBUG: applyToSelection=True, total nodes={len(all_nodes)}, selected={len(selected_nodes)}")
        
        # Filter out the currently edited group node itself (Issue #2)
        if path and len(path) > 0:
            # The last item in path is the currently edited group node
            edited_node = path[-1].node if hasattr(path[-1], 'node') else None
            if edited_node and edited_node in selected_nodes:
                selected_nodes.remove(edited_node)
                print(f"DEBUG: Removed edited group node '{edited_node.name}' from selection")
        if len(selected_nodes) == 0:
            return "No nodes selected. Please select at least one node or disable 'Selected Nodes Only'."
        nodes_to_process = selected_nodes
        # Create a set for fast lookup
        selected_set = set(selected_nodes)
        # Filter links to only include those between selected nodes
        filtered_links = [link for link in nodeTree.links 
                         if link.from_node in selected_set and link.to_node in selected_set]
        print(f"DEBUG: Total links in tree: {len(nodeTree.links)}, filtered links: {len(filtered_links)}")
    else:
        nodes_to_process = all_nodes
        filtered_links = list(nodeTree.links)
    
    # Create source node map with filtered links
    srcNodeMap = {}
    for link in filtered_links:
        srcLinkInfo = srcNodeMap.get(link.from_node)
        if srcLinkInfo is None:
            srcLinkInfo = SrcLinkInfo()
            srcNodeMap[link.from_node] = srcLinkInfo
        srcLinkInfo.addLinkCnt(link.to_node)
    
    nodeGraph = []
    nodes = nodes_to_process
    srcNodes = {n for n in nodes if n in srcNodeMap}
    pureDestNodes = [n for n in nodes if n not in srcNodes]
    processNodes(
        srcNodeMap,
        nodeGraph,
        nodeTree,
        None,
        pureDestNodes,
        0,
        arrangeType,
        maxColNodes,
        filtered_links,
    )
    groupNodes = displayNodes(nodeGraph, vAlign, xOffset, yOffset)
    if includeGroup:
        processedTrees = set()
        for node in groupNodes:
            nodeTree.nodes.active = node
            override = getOverride()
            if override is None:
                # Skip group processing if NODE_EDITOR not available
                print("Warning: Skipping group node processing - NODE_EDITOR area not found.")
                break
            with bpy.context.temp_override(**override):
                bpy.ops.node.group_edit(exit=False)
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                childNodeTree = node.node_tree
                if childNodeTree not in processedTrees:
                    displayTree(
                        childNodeTree,
                        vAlign,
                        xOffset,
                        yOffset,
                        includeGroup,
                        arrangeType,
                        maxColNodes,
                        applyToSelection,
                        None,  # Groups have their own path context
                    )
                    processedTrees.add(childNodeTree)
            with bpy.context.temp_override(**override):
                bpy.ops.node.group_edit(exit=True)
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)


def main(context, vAlign, xOffset, yOffset, includeGroup, arrangeType, maxColNodes, applyToSelection=False):
    nodeTree, error, path = getActiveNodeTree(context)
    if error:
        return error
    error = displayTree(
        nodeTree, vAlign, xOffset, yOffset, includeGroup, arrangeType, maxColNodes, applyToSelection, path
    )
    return error


class LineupNodesParams(PropertyGroup):
    vAlign: EnumProperty(
        name="Vertical Alignment",
        description="Alignment nodes with tops at same level",
        items=(
            ("TOP", "Top", "Align top level of nodes"),
            ("MIDDLE", "Middle", "Align middle of nodes"),
            ("BOTTOM", "Bottom", "Align bottom   level of nodes"),
        ),
        default="MIDDLE",
    )
    arrangeType: EnumProperty(
        name="Arrange By",
        description="Arrange by nature of links",
        items=(
            ("FIRST", "First", "Put at first link column"),
            ("LAST", "Last", "Put at last link column"),
            ("MAX", "Max", "Put where links are maximum"),
        ),
        default="LAST",
    )
    xOffset: IntProperty(
        name="Width Separation",
        default=50,
        description="Separation between node columns",
    )

    yOffset: IntProperty(
        name="Height Separation", default=50, description="Separation between node rows"
    )

    includeGroup: BoolProperty(
        name="Include Group", default=True, description="Lineup group node tree"
    )

    maxColNodes: IntProperty(
        name="Max Column Nodes",
        default=10,
        description="Maximum count of nodes within column",
    )

    applyToSelection: BoolProperty(
        name="Selected Nodes Only",
        default=False,
        description="Arrange only selected nodes (if True) or all nodes (if False)",
    )

    searchPattern: bpy.props.StringProperty(
        name="Search",
        default="",
        description="Search nodes by name (leave empty to show all)",
    )


class LineupNodesPanel(Panel):
    bl_label = "Line Up Nodes"
    bl_idname = "OBJECT_PT_lineupnodes"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Edit"

    @staticmethod
    def drawPanel(col):
        params = bpy.context.window_manager.lineupNodeParams
        col.prop(params, "vAlign")
        col.prop(params, "arrangeType")
        col.prop(params, "xOffset")
        col.prop(params, "yOffset")
        col.prop(params, "maxColNodes")
        col.prop(params, "includeGroup")
        col.prop(params, "applyToSelection")

    def draw(self, context):
        col = self.layout.column()
        LineupNodesPanel.drawPanel(col)
        
        # T013: Search/Filter section
        col.separator()
        box = col.box()
        box.label(text="Search Nodes:")
        box.prop(bpy.context.window_manager.lineupNodeParams, "searchPattern")
        box.operator("object.khema_searchnodes", text="Find Nodes", icon='VIEWZOOM')
        
        col.separator()
        col.operator("object.khema_lineupnodes")


class SearchNodesOp(Operator):
    """Search and select nodes by name"""
    bl_idname = "object.khema_searchnodes"
    bl_label = "Find Nodes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        nodeTree, error, path = getActiveNodeTree(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        params = bpy.context.window_manager.lineupNodeParams
        pattern = params.searchPattern.lower()
        
        if not pattern:
            self.report({'INFO'}, "Enter a search pattern first")
            return {'CANCELLED'}
        
        # Search and select matching nodes
        matches = []
        for node in nodeTree.nodes:
            node.select = False  # Deselect all first
            # Check name (internal ID), label (custom user label), and bl_label (displayed type name)
            search_fields = [
                node.name.lower(),
                node.label.lower() if node.label else "",
                node.bl_label.lower() if hasattr(node, 'bl_label') else ""
            ]
            if any(pattern in field for field in search_fields):
                node.select = True
                matches.append(node)
        
        if matches:
            # Focus on first match
            if hasattr(nodeTree.nodes, 'active'):
                nodeTree.nodes.active = matches[0]
            self.report({'INFO'}, f"Found {len(matches)} node(s) matching '{params.searchPattern}'")
        else:
            self.report({'WARNING'}, f"No nodes found matching '{params.searchPattern}'")
        
        return {'FINISHED'}


class LineupNodesOp(Operator):
    bl_idname = "object.khema_lineupnodes"
    bl_label = "Line Up Nodes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        params = bpy.context.window_manager.lineupNodeParams
        error = main(
            context,
            params.vAlign,
            params.xOffset,
            params.yOffset,
            params.includeGroup,
            params.arrangeType,
            params.maxColNodes,
            params.applyToSelection,
        )
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        return {'FINISHED'}


def register():
    bpy.utils.register_class(LineupNodesPanel)
    bpy.utils.register_class(SearchNodesOp)
    bpy.utils.register_class(LineupNodesOp)

    bpy.utils.register_class(LineupNodesParams)
    bpy.types.WindowManager.lineupNodeParams = bpy.props.PointerProperty(
        type=LineupNodesParams
    )


def unregister():
    del bpy.types.WindowManager.lineupNodeParams
    bpy.utils.unregister_class(LineupNodesParams)

    bpy.utils.unregister_class(LineupNodesOp)
    bpy.utils.unregister_class(SearchNodesOp)
    bpy.utils.unregister_class(LineupNodesPanel)
