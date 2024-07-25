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
    obj = context.active_object
    uitype = context.area.ui_type
    nodeTree = None
    if uitype == "ShaderNodeTree":
        return obj.active_material.node_tree
    elif uitype == "GeometryNodeTree":
        return obj.modifiers.active.node_group
    elif uitype == "CompositorNodeTree":
        return context.scene.node_tree
    return nodeTree


def processNodes(
    srcNodeMap, nodeGraph, nodeTree, destNode, srcNodes, depth, arrangeType, maxColNodes
):
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

        nodeGraph.append([])
        nodeColumn = nodeGraph[depth]
        nodeColumn.append(node)
        srcNodes = {k.from_node for k in nodeTree.links if k.to_node == node}
        processNodes(
            srcNodeMap,
            nodeGraph,
            nodeTree,
            node,
            srcNodes,
            depth + 1,
            arrangeType,
            maxColNodes,
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
    win = bpy.context.window
    screen = win.screen
    area = [a for a in screen.areas if a.type == "NODE_EDITOR"][0]
    region = [region for region in area.regions if region.type == "WINDOW"]
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
    nodeTree, vAlign, xOffset, yOffset, includeGroup, arrangeType, maxColNodes
):
    srcNodeMap = createSrcNodeMap(nodeTree)
    # print(srcNodeMap)
    nodeGraph = []
    nodes = nodeTree.nodes
    srcNodes = {n for n in nodes if (n in {k.from_node for k in nodeTree.links})}
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
    )
    groupNodes = displayNodes(nodeGraph, vAlign, xOffset, yOffset)
    if includeGroup:
        for node in groupNodes:
            nodeTree.nodes.active = node
            override = getOverride()
            with bpy.context.temp_override(**override):
                bpy.ops.node.group_edit(exit=False)
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                childNodeTree = node.node_tree
                displayTree(
                    childNodeTree,
                    vAlign,
                    xOffset,
                    yOffset,
                    includeGroup,
                    arrangeType,
                    maxColNodes,
                )
            with bpy.context.temp_override(**override):
                bpy.ops.node.group_edit(exit=True)
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)


def main(context, vAlign, xOffset, yOffset, includeGroup, arrangeType, maxColNodes):
    nodeTree = getActiveNodeTree(context)
    displayTree(
        nodeTree, vAlign, xOffset, yOffset, includeGroup, arrangeType, maxColNodes
    )


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

    def draw(self, context):
        col = self.layout.column()
        LineupNodesPanel.drawPanel(col)
        col.operator("object.khema_lineupnodes")


class LineupNodesOp(Operator):
    bl_idname = "object.khema_lineupnodes"
    bl_label = "Line Up Nodes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        params = bpy.context.window_manager.lineupNodeParams
        main(
            context,
            params.vAlign,
            params.xOffset,
            params.yOffset,
            params.includeGroup,
            params.arrangeType,
            params.maxColNodes,
        )
        return {"FINISHED"}


def register():
    bpy.utils.register_class(LineupNodesPanel)
    bpy.utils.register_class(LineupNodesOp)

    bpy.utils.register_class(LineupNodesParams)
    bpy.types.WindowManager.lineupNodeParams = bpy.props.PointerProperty(
        type=LineupNodesParams
    )


def unregister():
    del bpy.types.WindowManager.lineupNodeParams
    bpy.utils.unregister_class(LineupNodesParams)

    bpy.utils.unregister_class(LineupNodesOp)
    bpy.utils.unregister_class(LineupNodesPanel)
