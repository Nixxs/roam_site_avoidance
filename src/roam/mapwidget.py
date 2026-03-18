import math
from collections import defaultdict
from functools import partial

from PyQt5.QtCore import pyqtProperty
from qgis.PyQt.QtCore import Qt, QSize, QPropertyAnimation, QObject, QThread, \
    QRectF, QLocale, QPointF, QEvent
from qgis.PyQt.QtGui import QPixmap, QCursor, QIcon, QColor, QPen, QPolygon, QFont, QFontMetrics, QBrush, \
    QPainterPath, QPainter
from qgis.PyQt.QtSvg import QGraphicsSvgItem
from qgis.PyQt.QtWidgets import QActionGroup, QFrame, QWidget, QSizePolicy, \
    QAction, QMainWindow, QGraphicsItem, QToolButton, QLabel, QToolBar
from qgis.core import QgsMapLayer, Qgis, QgsRectangle, QgsProject, QgsApplication, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPoint, QgsCsException, QgsDistanceArea, QgsWkbTypes, \
    QgsGeometry, QgsSpatialIndex, QgsFeatureRequest, QgsUnitTypes
from qgis.gui import QgsMapToolZoom, QgsRubberBand, QgsScaleComboBox, \
    QgsLayerTreeMapCanvasBridge, \
    QgsMapCanvasSnappingUtils, QgsMapToolPan

import roam.api.utils
import roam.config
import roam.utils
from roam import roam_style
from roam.api import plugins
from roam.api.events import RoamEvents
from roam.biglist import BigList
from roam.gps_action import GPSAction, GPSMarker
from roam.maptools import InfoTool
from roam.popupdialogs import PickActionDialog


class SnappingUtils(QgsMapCanvasSnappingUtils):
    def prepareIndexStarting(self, count):
        pass

    def prepareIndexProgress(self, index):
        pass

        def set_custom_text(self, text: str, other_text: str, show: bool = True) -> None:
            """
            Set the current custom text and optionally show it on the canvas.
            :param text: The text to store/display.
            :param other_text: Additional text to display.
            :param show: If True, display immediately.
            """
            combined = text or ""
            if other_text:
                combined = f"{combined} — {other_text}" if combined else other_text
            self._custom_text = combined
class NorthArrow(QGraphicsSvgItem):
    def __init__(self, path, canvas, parent=None):
        super(NorthArrow, self).__init__(path, parent)
        self.canvas = canvas
        self.setTransformOriginPoint(self.boundingRect().width() / 2, self.boundingRect().height() / 2)

    def paint(self, painter, styleoptions, widget=None):
        angle = self._calc_north()
        if angle:
            self.setRotation(angle)
        super(NorthArrow, self).paint(painter, styleoptions, widget)

    def _calc_north(self):
        extent = self.canvas.extent()
        if self.canvas.layerCount() == 0 or extent.isEmpty():
            return 0

        outcrs = self.canvas.mapSettings().destinationCrs()

        if outcrs.isValid() and not outcrs.geographicFlag():
            crs = QgsCoordinateReferenceSystem()
            crs.createFromOgcWmsCrs("EPSG:4326")

            transform = QgsCoordinateTransform(outcrs, crs)

            p1 = QgsPoint(extent.center())
            p2 = QgsPoint(p1.x(), p1.y() + extent.height() * 0.25)

            try:
                pp1 = transform.transform(p1)
                pp2 = transform.transform(p2)
            except QgsCsException:
                roam.utils.warning("North arrow. Error transforming.")
                return None

            area = QgsDistanceArea()
            area.setEllipsoid(crs.ellipsoidAcronym())
            area.setEllipsoidalMode(True)
            area.setSourceCrs(crs)
            distance, angle, _ = area.computeDistanceBearing(pp1, pp2)
            angle = math.degrees(angle)
            return angle
        else:
            return 0


class ScaleBarItem(QGraphicsItem):
    def __init__(self, canvas, parent=None):
        super(ScaleBarItem, self).__init__(parent)
        self.canvas = canvas
        self.realsize = 100
        black = QColor(Qt.black)
        black.setAlpha(150)
        white = QColor(Qt.white)
        white.setAlpha(150)
        blackpen = QPen(black, 4)
        whitepen = QPen(white, 8)
        self.pens = [whitepen, blackpen]
        self.whitepen = QPen(white, 1)
        self.blackbrush = QBrush(black)
        self.ticksize = 10
        self.fontsize = 15
        self.font = QFont()
        self.font.setPointSize(self.fontsize)
        self.font.setStyleHint(QFont.Times, QFont.PreferAntialias)
        self.font.setBold(True)
        self.metrics = QFontMetrics(self.font)

    def boundingRect(self):
        try:
            width, realsize, label, fontsize = self._calc_size()
            halfheight = (self.ticksize + fontsize[1]) / 2
            halfwidth = (width + fontsize[0]) / 2
            return QRectF(-halfwidth, -halfheight, halfwidth, halfheight)
        except ZeroDivisionError:
            return QRectF()

    def paint(self, painter, styleoptions, widget=None):
        try:
            width, realsize, label, fontsize = self._calc_size()
        except ZeroDivisionError:
            return

        mapunits = self.canvas.mapUnits()

        # painter.drawRect(self.boundingRect())
        array = QPolygon()
        canvasheight = self.canvas.height()
        canvaswidth = self.canvas.width()
        margin = 20
        originy = 0
        originx = 0

        self.setPos(margin, canvasheight - margin)

        x1, y1 = originx, originy
        x2, y2 = originx, originy + self.ticksize
        x3, y3 = originx + width, originy + self.ticksize
        midx, midy = originx + width / 2, originy + self.ticksize / 2
        x4, y4 = originx + width, originy

        for pen in self.pens:
            painter.setPen(pen)
            # Drwa the scale bar
            painter.drawLine(x1, y1, x2, y2)
            painter.drawLine(x2, y2, x3, y3)
            painter.drawLine(x3, y3, x4, y4)
            painter.drawLine(midx, midy, midx, y1)

        # Draw the text
        fontwidth = self.metrics.width("0")
        fontheight = self.metrics.height()
        fontheight /= 2
        fontwidth /= 2
        path = QPainterPath()
        point = QPointF(x1 - fontwidth, y1 - fontheight)
        path.addText(point, self.font, "0")
        painter.setPen(self.whitepen)
        painter.setBrush(self.blackbrush)
        painter.setRenderHints(QPainter.Antialiasing)
        painter.setFont(self.font)
        painter.drawPath(path)

        fontwidth = self.metrics.width(label)
        fontheight = self.metrics.height()
        fontheight /= 2
        fontwidth /= 2
        point = QPointF(x4 - fontwidth, y4 - fontheight)
        path.addText(point, self.font, label)
        painter.drawPath(path)

    def _calc_size(self):
        realSize = self.realsize
        canvaswidth = self.canvas.width()
        mapunitsperpixel = abs(self.canvas.mapUnitsPerPixel())
        mapunits = self.canvas.mapUnits()
        prefered_units = roam.config.settings.get("prefer_units", "meters")
        newunits = Qgis.fromLiteral(prefered_units, Qgis.Meters)
        mapunitsperpixel *= Qgis.fromUnitToUnitFactor(mapunits, newunits)
        mapunits = newunits

        # Convert the real distance into pixels
        barwidth = realSize / mapunitsperpixel

        if barwidth < 30:
            barwidth = canvaswidth / 4

        while barwidth > canvaswidth / 3:
            barwidth /= 3

        realSize = barwidth * mapunitsperpixel

        # Round
        powerof10 = math.floor(math.log10(realSize))
        scaler = math.pow(10.0, powerof10)
        realSize = round(realSize / scaler) * scaler
        barwidth = realSize / mapunitsperpixel
        label, realSize = self._label_size(mapunits, realSize)
        metrics = QFontMetrics(self.font)
        fontwidth = metrics.width(label)
        fontheight = metrics.height()

        sizelabel = QLocale.system().toString(realSize)
        sizelabel = "{} {}".format(sizelabel, label)

        barwidth = self._adjust_bar_size(barwidth, mapunits)
        barwidth = barwidth + fontwidth

        return barwidth, realSize, sizelabel, (fontwidth, fontheight)

    def _label_size(self, unit, currentsize):
        if unit == Qgis.Meters:
            if currentsize > 1000:
                return "km", currentsize / 1000
            elif currentsize < 0.01:
                return "mm", currentsize * 1000
            elif currentsize < 0.1:
                return "cm", currentsize * 100
            else:
                return "m", currentsize
        elif unit == Qgis.Feet:
            print(currentsize)
            if currentsize > 5280.0:
                return "miles", currentsize / 5000
            elif currentsize == 5280.0:
                return "mile", currentsize / 5000
            elif currentsize < 1:
                return "inches", currentsize * 10
            elif currentsize == 1.0:
                return "foot", currentsize
            else:
                return "feet", currentsize
        elif unit == Qgis.Degrees:
            if currentsize == 1.0:
                return "degree", currentsize
            else:
                return "degrees", currentsize
        else:
            return str(unit), currentsize

    def _adjust_bar_size(self, barsize, unit):
        if unit == Qgis.Feet:
            if barsize > 5280.0 or barsize == 5280.0:
                return (barsize * 5290) / 5000
            elif barsize < 1:
                return (barsize * 10) / 12

        return barsize


class CurrentSelection(QgsRubberBand):
    """
    Position marker for the current location in the viewer.
    """

    class AniObject(QObject):
        def __init__(self, band):
            super(CurrentSelection.AniObject, self).__init__()
            self.color = QColor()

        @pyqtProperty(float)
        def alpha(self):
            return self.color.alpha()

        @alpha.setter
        def alpha(self, value):
            self.color.setAlpha(int(value))

    def __init__(self, canvas):
        super(CurrentSelection, self).__init__(canvas)
        self.outline = QgsRubberBand(canvas)
        self.outline.setBrushStyle(Qt.NoBrush)
        self.outline.setWidth(5)
        self.outline.setIconSize(30)
        self.aniobject = CurrentSelection.AniObject(self)
        self.anim = QPropertyAnimation(self.aniobject, "alpha".encode("utf-8"))
        self.anim.setDuration(500)
        self.anim.setStartValue(50)
        self.anim.setEndValue(100)
        self.anim.valueChanged.connect(self.value_changed)

    def setOutlineColour(self, color):
        self.outline.setColor(color)

    def setToGeometry(self, geom, layer):
        super(CurrentSelection, self).setToGeometry(geom, layer)
        self.outline.setToGeometry(geom, layer)
        self.anim.stop()
        self.anim.start()

    def reset(self, geomtype=QgsWkbTypes.LineGeometry):
        super(CurrentSelection, self).reset(geomtype)
        self.outline.reset(geomtype)
        self.anim.stop()

    def value_changed(self, value):
        self.setColor(self.aniobject.color)
        self.update()

    def setColor(self, color):
        self.aniobject.color = color
        super(CurrentSelection, self).setColor(color)


from roam.ui.ui_mapwidget import Ui_CanvasWidget


class MapWidget(Ui_CanvasWidget, QMainWindow):
    def __init__(self, parent=None):
        super(MapWidget, self).__init__(parent)
        self.setupUi(self)
        self.snapping = True

        icon = roam_style.iconsize()
        self.projecttoolbar.setIconSize(QSize(icon, icon))

        self.defaultextent = None
        self.current_form = None
        self.last_form = None
        self.layerbuttons = []
        self.editfeaturestack = []
        self.lastgpsposition = None
        self.project = None
        self.gps = None
        self.gpslogging = None
        self.selectionbands = defaultdict(partial(QgsRubberBand, self.canvas))
        self._spatial_indexes = {}

        self.bridge = QgsLayerTreeMapCanvasBridge(QgsProject.instance().layerTreeRoot(), self.canvas)
        self.bridge.setAutoSetupOnFirstLayer(False)

        self.canvas.setCanvasColor(Qt.white)
        self.canvas.enableAntiAliasing(True)

        self.snappingutils = SnappingUtils(self.canvas, self)
        self.canvas.setSnappingUtils(self.snappingutils)

        threadcount = QThread.idealThreadCount()
        threadcount = 2 if threadcount > 2 else 1
        QgsApplication.setMaxThreads(threadcount)
        self.canvas.setParallelRenderingEnabled(True)

        self.canvas.setFrameStyle(QFrame.NoFrame)

        self.editgroup = QActionGroup(self)
        self.editgroup.setExclusive(True)
        self.editgroup.addAction(self.actionPan)
        self.editgroup.addAction(self.actionZoom_In)
        self.editgroup.addAction(self.actionZoom_Out)
        self.editgroup.addAction(self.actionInfo)

        self.actionGPS = GPSAction(self.canvas, self)
        self.projecttoolbar.addAction(self.actionGPS)

        if roam.config.settings.get('north_arrow', False):
            self.northarrow = NorthArrow(":/icons/north", self.canvas)
            self.northarrow.setPos(10, 10)
            self.canvas.scene().addItem(self.northarrow)

        smallmode = roam.config.settings.get("smallmode", False)
        self.projecttoolbar.setSmallMode(smallmode)

        self.projecttoolbar.setContextMenuPolicy(Qt.CustomContextMenu)

        gpsspacewidget = QWidget()
        gpsspacewidget.setMinimumWidth(30)
        gpsspacewidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.topspaceraction = self.projecttoolbar.insertWidget(self.actionGPS, gpsspacewidget)

        self.dataentryselection = QAction(self.projecttoolbar)
        self.dataentryaction = self.projecttoolbar.insertAction(self.topspaceraction, self.dataentryselection)
        self.dataentryselection.triggered.connect(self.select_data_entry)

        self.gpsMarker = GPSMarker(self.canvas)
        self.gpsMarker.hide()

        self.currentfeatureband = CurrentSelection(self.canvas)
        self.currentfeatureband.setIconSize(30)
        self.currentfeatureband.setWidth(10)
        self.currentfeatureband.setColor(QColor(88, 64, 173, 50))
        self.currentfeatureband.setOutlineColour(QColor(88, 64, 173))

        self.gpsband = QgsRubberBand(self.canvas)
        self.gpsband.setColor(QColor(165, 111, 212, 75))
        self.gpsband.setWidth(5)

        RoamEvents.refresh_map.connect(self.refresh_map)
        RoamEvents.editgeometry.connect(self.queue_feature_for_edit)
        RoamEvents.selectioncleared.connect(self.clear_selection)
        RoamEvents.selectionchanged.connect(self.highlight_selection)
        RoamEvents.openfeatureform.connect(self.feature_form_loaded)
        RoamEvents.sync_complete.connect(self.refresh_map)
        RoamEvents.snappingChanged.connect(self.snapping_changed)

        self.snappingbutton = QToolButton()
        self.snappingbutton.setText("Snapping: On")
        self.snappingbutton.setAutoRaise(True)
        self.snappingbutton.pressed.connect(self.toggle_snapping)

        spacer = QWidget()
        spacer2 = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        spacer2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.scalewidget = QgsScaleComboBox()

        self.scalebutton = QToolButton()
        self.scalebutton.setAutoRaise(True)
        self.scalebutton.setMaximumHeight(self.statusbar.height())
        self.scalebutton.pressed.connect(self.selectscale)
        self.scalebutton.setText("Scale")

        self.scalelist = BigList(parent=self.canvas, centeronparent=True, showsave=False)
        self.scalelist.hide()
        self.scalelist.setlabel("Map Scale")
        self.scalelist.setmodel(self.scalewidget.model())
        self.scalelist.closewidget.connect(self.scalelist.close)
        self.scalelist.itemselected.connect(self.update_scale_from_item)
        self.scalelist.itemselected.connect(self.scalelist.close)

        self.positionlabel = QLabel('')
        self.gpslabel = QLabel("GPS: Not active")
        self.gpslabelposition = QLabel("")

        self.statusbar.addWidget(self.snappingbutton)
        self.statusbar.addWidget(spacer2)
        self.statusbar.addWidget(self.gpslabel)
        self.statusbar.addWidget(self.gpslabelposition)
        self.statusbar.addPermanentWidget(self.scalebutton)

        self.canvas.extentsChanged.connect(self.update_status_label)
        self.canvas.scaleChanged.connect(self.update_status_label)

        self.connectButtons()

        scalebar_enabled = roam.config.settings.get('scale_bar', False)
        self.scalebar_enabled = False
        if scalebar_enabled:
            roam.utils.warning("Unsupported feature: Scale bar support not ported to QGIS 3 API yet.")
            RoamEvents.raisemessage("Unsupported feature", "Scale bar support not ported to QGIS 3 API yet",
                                    level=RoamEvents.CRITICAL)
            self.scalebar_enabled = False
            # self.scalebar = ScaleBarItem(self.canvas)
            # self.canvas.scene().addItem(self.scalebar)

        # ---- Custom overlay to show arbitrary text (top-right) ----
        self._custom_text = ""
        self.customOverlay = QLabel(self.canvas)
        self.customOverlay.setStyleSheet(
            "background-color: rgba(0,0,0,120); color: white; padding: 4px 8px; border-radius: 4px;"
        )
        self.customOverlay.setVisible(False)
        self.canvas.installEventFilter(self)

        # Optional toolbar toggle to show/hide current custom text
        self.actionShowCustom = QAction("Show Value", self)
        self.actionShowCustom.setCheckable(True)
        self.actionShowCustom.toggled.connect(self._toggle_custom_overlay)
        self.projecttoolbar.addAction(self.actionShowCustom)

        # ---- GPS overlay (top-right) ----
        self.gpsOverlay = QLabel(self.canvas)
        self.gpsOverlay.setStyleSheet(
            "background-color: rgba(0,0,0,120); color: white; padding: 4px 8px; border-radius: 4px;"
        )
        self.gpsOverlay.setVisible(False)

        self.actionShowGPS = QAction("GPS XY", self)
        self.actionShowGPS.setCheckable(True)
        self.actionShowGPS.setChecked(True)
        self.actionShowGPS.toggled.connect(self._toggle_gps_overlay)
        self.projecttoolbar.addAction(self.actionShowGPS)

    def clear_plugins(self) -> None:
        """
        Clear all the plugin added toolbars from the map interface.
        """
        toolbars = self.findChildren(QToolBar)
        for toolbar in toolbars:
            if toolbar.property("plugin_toolbar"):
                toolbar.unload()
                self.removeToolBar(toolbar)
                toolbar.deleteLater()

    def add_plugins(self, pluginnames) -> None:
        """
        Add the given plugins to to the mapping interface.

        Adds the toolbars the plugin exposes as new toolbars for the user.
        :param pluginnames: The names of the plugins to load.  Must already be loaded
                            by the plugin loader
        """
        for name in pluginnames:
            # Get the plugin
            try:
                plugin_mod = plugins.loaded_plugins[name]
            except KeyError:
                continue

            if not hasattr(plugin_mod, 'toolbars'):
                roam.utils.warning("No toolbars() function found in {}".format(name))
                continue

            toolbars = plugin_mod.toolbars()
            self.load_plugin_toolbars(toolbars)

    def load_plugin_toolbars(self, toolbars):
        """
        Load the plugin toolbars into the mapping interface.
        :param toolbars: The list of toolbars class objects to load.
        :return:
        """
        for ToolBarClass in toolbars:
            toolbar = ToolBarClass(plugins.api, self)
            self.addToolBar(Qt.BottomToolBarArea, toolbar)
            toolbar.setProperty("plugin_toolbar", True)

    def snapping_changed(self, snapping):
        """
        Called when the snapping settings have changed. Updates the label in the status bar.
        :param snapping:
        """
        self.snapping = snapping
        if snapping:
            self.snappingbutton.setText("Snapping: On")
        else:
            self.snappingbutton.setText("Snapping: Off")

    def toggle_snapping(self):
        """
        Toggle snapping on or off.
        """
        self.snapping = not self.snapping
        try:
            self.canvas.mapTool().toggle_snapping()
        except AttributeError:
            pass

        RoamEvents.snappingChanged.emit(self.snapping)

    def selectscale(self):
        """
        Show the select scale widget.
        :return:
        """
        self.scalelist.show()

    def update_scale_from_item(self, index):
        """
        Update the canvas scale from the selected scale item.
        :param index: The index of the selected item.
        """
        scale, _ = self.scalewidget.toDouble(index.data(Qt.DisplayRole))
        self.canvas.zoomScale(1.0 / scale)

    def update_gps_fixed_label(self, fixed, gpsinfo):
        if not fixed:
            self.gpslabel.setText("GPS: Acquiring fix")
            self.gpslabelposition.setText("")
            self.gpsOverlay.setVisible(False)

    quality_mappings = {
        0: "invalid",
        1: "GPS",
        2: "DGPS",
        3: "PPS",
        4: "Real Time Kinematic",
        5: "Float RTK",
        6: "Estimated",
        7: "Manual input mode",
        8: "Simulation mode"
    }

    def update_gps_label(self, position, gpsinfo):
        """
        Update the GPS label in the status bar with the GPS status.
        :param position: The current GPS position.
        :param gpsinfo: The current extra GPS information.
        """
        if not self.gps.connected:
            return

        fixtype = self.quality_mappings.get(gpsinfo.quality, "")
        self.gpslabel.setText("DOP P:<b>{0:.2f}</b> H:<b>{1:.2f}</b> V:<b>{2:.2f}</b> "
                              "Fix: <b>{3}</b> "
                              "Sats: <b>{4}</b> ".format(gpsinfo.pdop,
                                                        gpsinfo.hdop,
                                                        gpsinfo.vdop,
                                                        fixtype,
                                                        gpsinfo.satellitesUsed))

        places = roam.config.settings.get("gpsplaces", 8)
        self.gpslabelposition.setText("X: <b>{x:.{places}f}</b> "
                                      "Y: <b>{y:.{places}f}</b> "
                                      "Z: <b>{z}m</b> ".format(x=position.x(),
                                                     y=position.y(),
                                                     z=gpsinfo.elevation,
                                                     places=places))

        # Update the GPS overlay with current XY if enabled
        if self.actionShowGPS.isChecked():
            overlay_text = f"X: {position.x():.{places}f}    Y: {position.y():.{places}f}"

            # Find nearest across all visible vector layers
            dist_all, nearest_layer = self._nearest_distance_across_layers(position)
            if dist_all is not None and nearest_layer is not None:
                overlay_text += f"    d: {dist_all:.1f} m ({nearest_layer.name()})"

            self.gpsOverlay.setText(overlay_text)
            self.gpsOverlay.setVisible(True)
            self._position_overlays()

    def gps_disconnected(self):
        self.gpslabel.setText("GPS: Not Active")
        self.gpslabelposition.setText("")
        self.gpsMarker.hide()
        self.gpsOverlay.setVisible(False)

    def zoom_to_feature(self, feature):
        """
        Zoom to the given feature in the map.
        :param feature:
        :return:
        """
        box = feature.geometry().boundingBox()
        xmin, xmax, ymin, ymax = box.xMinimum(), box.xMaximum(), box.yMinimum(), box.yMaximum()
        xmin -= 5
        xmax += 5
        ymin -= 5
        ymax += 5
        box = QgsRectangle(xmin, ymin, xmax, ymax)
        self.canvas.setExtent(box)
        self.canvas.refresh()

    def update_status_label(self, *args) -> None:
        """
        Update the status bar labels when the information has changed.
        """
        extent = self.canvas.extent()
        self.positionlabel.setText("Map Center: {}".format(extent.center().toString()))
        scale = 1.0 / self.canvas.scale()
        scale = self.scalewidget.toString(scale)
        self.scalebutton.setText(scale)

    def refresh_map(self) -> None:
        """
        Refresh the map
        """
        self.canvas.refresh()

    def updatescale(self) -> None:
        """
        Update the scale of the map with the current scale from the scale widget
        :return:
        """
        self.canvas.zoomScale(1.0 / self.scalewidget.scale())

    # ----- Custom text overlay API -----
    def set_custom_text(self, text: str, other_text: str, show: bool = True) -> None:
        """
        Set the current custom text and optionally show it on the canvas.
        :param text: The text to store/display.
        :param other_text: Additional text to display.
        :param show: If True, display immediately.
        """
        self._custom_text = text or ""
        self.customOverlay.setText(self._custom_text)
        if show and self._custom_text:
            self.actionShowCustom.setChecked(True)
            self._position_overlays()
            self.customOverlay.setVisible(True)
        elif not self._custom_text:
            self.actionShowCustom.setChecked(False)
            self.customOverlay.setVisible(False)

    def _toggle_custom_overlay(self, checked: bool) -> None:
        if checked and self._custom_text:
            self._position_overlays()
            self.customOverlay.setVisible(True)
        else:
            self.customOverlay.setVisible(False)

    def _position_overlays(self) -> None:
        margin = 10
        spacing = 6
        x_right = self.canvas.width() - margin

        y = margin
        # Order: GPS first, then custom text below it
        for label in (self.gpsOverlay, self.customOverlay):
            if not label.isVisible():
                continue
            label.adjustSize()
            w = label.width()
            label.move(max(0, x_right - w), y)
            y += label.height() + spacing

    def _toggle_gps_overlay(self, checked: bool) -> None:
        if checked and self.gpsOverlay.text():
            self.gpsOverlay.setVisible(True)
            self._position_overlays()
        else:
            self.gpsOverlay.setVisible(False)

    def _layer_is_visible(self, layer: QgsMapLayer) -> bool:
        try:
            node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
            return bool(node and node.isVisible())
        except Exception:
            return True

    def _get_spatial_index(self, layer):
        lid = layer.id()
        index = self._spatial_indexes.get(lid)
        if index is None:
            index = QgsSpatialIndex(layer.getFeatures())
            self._spatial_indexes[lid] = index
            # Invalidate on edits/changes (simple approach)
            try:
                layer.committedFeaturesAdded.connect(lambda *_: self._spatial_indexes.pop(lid, None))
                layer.committedFeaturesRemoved.connect(lambda *_: self._spatial_indexes.pop(lid, None))
                layer.geometryChanged.connect(lambda *_: self._spatial_indexes.pop(lid, None))
            except Exception:
                pass
        return index

    def _nearest_distance_across_layers(self, position):
        """
        Compute the nearest distance (meters) from position to any visible vector layer's nearest feature.
        :return: (distance_meters: float | None, layer: QgsMapLayer | None)
        """
        best_dist = None
        best_layer = None
        for layer in roam.api.utils.layers():
            if layer.type() != QgsMapLayer.VectorLayer:
                continue
            if not self._layer_is_visible(layer):
                continue
            # Quick NN via spatial index
            try:
                index = self._get_spatial_index(layer)
                nearest_ids = index.nearestNeighbor(position, 1)
                if not nearest_ids:
                    continue
                fid = nearest_ids[0]
                for f in layer.getFeatures(QgsFeatureRequest(fid)):
                    geom = QgsGeometry(f.geometry())
                    transform = self.canvas.mapSettings().layerTransform(layer)
                    if transform and transform.isValid():
                        try:
                            geom.transform(transform)
                        except Exception:
                            continue
                    d = geom.distance(QgsGeometry.fromPointXY(position))
                    if best_dist is None or d < best_dist:
                        best_dist = d
                        best_layer = layer
            except Exception:
                continue

        if best_dist is None:
            return None, None

        try:
            factor = QgsUnitTypes.fromUnitToUnitFactor(self.canvas.mapUnits(), QgsUnitTypes.DistanceMeters)
        except Exception:
            try:
                factor = Qgis.fromUnitToUnitFactor(self.canvas.mapUnits(), Qgis.Meters)
            except Exception:
                factor = 1.0
        return best_dist * factor, best_layer

    def _nearest_distance_to_layer(self, position, layer):
        """
        Compute distance (in meters) from map position (map CRS) to the nearest feature of the given layer.
        This is a simple per-feature scan; for large layers a spatial index would be better.
        :param position: QgsPointXY in map/canvas CRS.
        :param layer: QgsVectorLayer to measure against.
        :return: (distance_meters: float | None, nearest_feature)
        """
        try:
            transform = self.canvas.mapSettings().layerTransform(layer)
        except Exception:
            transform = None

        point_geom = QgsGeometry.fromPointXY(position)
        mindist = None
        nearest = None
        for f in layer.getFeatures():
            geom = QgsGeometry(f.geometry())
            if transform and transform.isValid():
                try:
                    geom.transform(transform)
                except Exception:
                    continue
            d = geom.distance(point_geom)
            if mindist is None or d < mindist:
                mindist = d
                nearest = f

        if mindist is None:
            return None, None

        try:
            factor = QgsUnitTypes.fromUnitToUnitFactor(self.canvas.mapUnits(), QgsUnitTypes.DistanceMeters)
        except Exception:
            try:
                factor = Qgis.fromUnitToUnitFactor(self.canvas.mapUnits(), Qgis.Meters)
            except Exception:
                factor = 1.0
        return mindist * factor, nearest

    def eventFilter(self, obj, event):
        if obj is self.canvas and event.type() == QEvent.Resize:
            self._position_overlays()
        return super(MapWidget, self).eventFilter(obj, event)

    @property
    def crs(self) -> QgsCoordinateReferenceSystem:
        """
        Get the CRS used that is being used in the canvas
        :return: The QgsCoordinateReferenceSystem that is used by the canvas
        """
        return self.canvas.mapSettings().destinationCrs()

    def feature_form_loaded(self, form, feature, *args):
        """
        Called when the feature form is loaded.
        :param form: The Form object. Holds a reference to the forms layer.
        :param feature: The current capture feature
        """
        self.currentfeatureband.setToGeometry(feature.geometry(), form.QGISLayer)

    def highlight_selection(self, results):
        """
        Highlight the selection on the canvas.  This updates all selected objects based on the result set.
        :param results: A dict-of-list of layer-features.
        """
        self.clear_selection()
        for layer, features in results.items():
            band = self.selectionbands[layer]
            band.setColor(QColor(255, 0, 0))
            band.setIconSize(25)
            band.setWidth(5)
            band.setBrushStyle(Qt.NoBrush)
            band.reset(layer.geometryType())
            band.setZValue(self.currentfeatureband.zValue() - 1)
            for feature in features:
                band.addGeometry(feature.geometry(), layer)
        self.canvas.update()

    def highlight_active_selection(self, layer, feature, features):
        """
        Update the current active selected feature.
        :param layer: The layer of the active feature.
        :param feature: The active feature.
        :param features: The other features in the set to show as non active selection.
        :return:
        """
        self.clear_selection()
        self.highlight_selection({layer: features})
        self.currentfeatureband.setToGeometry(feature.geometry(), layer)
        self.canvas.update()

    def clear_selection(self):
        """
        Clear the selection from the canvas. Resets all selection rubber bands.
        :return:
        """
        # Clear the main selection rubber band
        self.canvas.scene().update()
        self.currentfeatureband.reset()
        # Clear the rest
        for band in self.selectionbands.values():
            band.reset()

        self.canvas.update()
        self.editfeaturestack = []

    def queue_feature_for_edit(self, form, feature):
        """
        Push a feature on the edit stack so the feature can have the geometry edited.
        :note: This is a big hack and I don't like it!
        :param form: The form for the current feature
        :param feature: The active feature.
        """

        def trigger_default_action():
            for action in self.projecttoolbar.actions():
                if action.property('dataentry') and action.isdefault:
                    action.trigger()
                    self.canvas.currentLayer().startEditing()
                    self.canvas.mapTool().setEditMode(True, feature.geometry(), feature)
                    break

        self.editfeaturestack.append((form, feature))
        self.save_current_form()
        self.load_form(form)
        trigger_default_action()

    def save_current_form(self):
        self.last_form = self.current_form

    def restore_last_form(self):
        self.load_form(self.last_form)

    def clear_temp_objects(self):
        """
        Clear all temp objects from the canvas.
        :return:
        """

        def clear_tool_band():
            """
            Clear the rubber band of the active tool if it has one
            """
            tool = self.canvas.mapTool()
            if hasattr(tool, "clearBand"):
                tool.clearBand()

        self.currentfeatureband.reset()
        clear_tool_band()

    def settings_updated(self, settings):
        """
        Called when the settings have been updated in the Roam config.
        :param settings: A dict of the settings.
        """
        self.actionGPS.updateGPSPort()
        gpslogging = settings.get('gpslogging', True)
        if self.gpslogging:
            self.gpslogging.logging = gpslogging
        smallmode = settings.get("smallmode", False)
        self.projecttoolbar.setSmallMode(smallmode)

    def set_gps(self, gps, logging):
        """
        Set the GPS for the map widget.  Connects GPS signals
        """
        self.gps = gps
        self.gpslogging = logging
        self.gps.gpsfixed.connect(self.update_gps_fixed_label)
        self.gps.gpsposition.connect(self.update_gps_label)
        self.gps.gpsposition.connect(self.gps_update_canvas)
        self.gps.firstfix.connect(self.gps_first_fix)
        self.gps.gpsdisconnected.connect(self.gps_disconnected)

        self.gpsMarker.setgps(self.gps)
        self.actionGPS.setgps(gps)

    def gps_update_canvas(self, position, gpsinfo):
        """
        Updates the map canvas based on the GPS position.  By default if the GPS is outside the canvas
        extent the canvas will move to center on the GPS.  Can be turned off in settings.
        :param postion: The current GPS position.
        :param gpsinfo: The extra GPS information
        """
        # Recenter map if we go outside of the 95% of the area
        if self.gpslogging.logging:
            self.gpsband.addPoint(position)
            self.gpsband.show()

        if roam.config.settings.get('gpscenter', True):
            if not self.lastgpsposition == position:
                self.lastgpsposition = position
                rect = QgsRectangle(position, position)
                extentlimt = QgsRectangle(self.canvas.extent())
                extentlimt.scale(0.95)

                if not extentlimt.contains(position):
                    self.zoom_to_location(position)

        self.gpsMarker.show()
        self.gpsMarker.setCenter(position, gpsinfo)

    def gps_first_fix(self, postion, gpsinfo):
        """
        Called the first time the GPS gets a fix.  If set this will zoom to the GPS after the first fix
        :param postion: The current GPS position.
        :param gpsinfo: The extra GPS information
        """
        zoomtolocation = roam.config.settings.get('gpszoomonfix', True)
        if zoomtolocation:
            self.canvas.zoomScale(1000)
            self.zoom_to_location(postion)
        # Make sure overlay shows on first fix if enabled
        if self.actionShowGPS.isChecked():
            self.gpsOverlay.setVisible(True)
            self._position_overlays()

    def zoom_to_location(self, position):
        """
        Zoom to ta given position on the map..
        """
        rect = QgsRectangle(position, position)
        self.canvas.setExtent(rect)
        self.canvas.refresh()

    def select_data_entry(self):
        """
        Open the form selection widget to allow the user to pick the active capture form.
        """

        def showformerror(form):
            pass

        def actions():
            for form in self.project.forms:
                if not self.form_valid_for_capture(form):
                    continue

                action = form.createuiaction()
                valid, failreasons = form.valid
                if not valid:
                    roam.utils.warning("Form {} failed to load".format(form.label))
                    roam.utils.warning("Reasons {}".format(failreasons))
                    action.triggered.connect(partial(showformerror, form))
                else:
                    action.triggered.connect(partial(self.load_form, form))
                yield action

        formpicker = PickActionDialog(msg="Select data entry form", wrap=5)
        formpicker.addactions(actions())
        formpicker.exec_()

    def project_loaded(self, project):
        """
        Called when the project is loaded. Main entry point for a loade project.
        :param project: The Roam project that has been loaded.
        """
        self.snappingutils.setConfig(QgsProject.instance().snappingConfig())
        self.project = project
        self.actionPan.trigger()
        firstform = self.first_capture_form()
        if firstform:
            self.load_form(firstform)
            self.dataentryselection.setVisible(True)
        else:
            self.dataentryselection.setVisible(False)

        # Enable the raster layers button only if the project contains a raster layer.
        layers = roam.api.utils.layers()
        hasrasters = any(layer.type() == QgsMapLayer.RasterLayer for layer in layers)
        self.actionRaster.setEnabled(hasrasters)
        self.defaultextent = self.canvas.extent()
        roam.utils.info("Extent: {}".format(self.defaultextent.toString()))

        self.infoTool.selectionlayers = project.selectlayersmapping()

        self.canvas.refresh()

        projectscales, _ = QgsProject.instance().readBoolEntry("Scales", "/useProjectScales")
        if projectscales:
            projectscales, _ = QgsProject.instance().readListEntry("Scales", "/ScalesList")

            self.scalewidget.updateScales(projectscales)
        else:
            scales = ["1:50000", "1:25000", "1:10000", "1:5000",
                      "1:2500", "1:1000", "1:500", "1:250", "1:200", "1:100"]
            scales = roam.config.settings.get('scales', scales)
            self.scalewidget.updateScales(scales)

        if self.scalebar_enabled:
            self.scalebar.update()

        red = QgsProject.instance().readNumEntry("Gui", "/CanvasColorRedPart", 255)[0]
        green = QgsProject.instance().readNumEntry("Gui", "/CanvasColorGreenPart", 255)[0]
        blue = QgsProject.instance().readNumEntry("Gui", "/CanvasColorBluePart", 255)[0]
        myColor = QColor(red, green, blue)
        self.canvas.setCanvasColor(myColor)

        self.actionPan.toggle()
        self.clear_plugins()
        self.add_plugins(project.enabled_plugins)

    def setMapTool(self, tool, *args):
        """
        Set the active map tool in the canvas.
        :param tool: The QgsMapTool to set.
        """
        if tool == self.canvas.mapTool():
            return

        if hasattr(tool, "setSnapping"):
            tool.setSnapping(self.snapping)
        self.canvas.setMapTool(tool)

    def connectButtons(self):
        """
        Connect the default buttons in the interface. Zoom, pan, etc
        """

        def connectAction(action, tool):
            action.toggled.connect(partial(self.setMapTool, tool))

        def cursor(name):
            pix = QPixmap(name)
            pix = pix.scaled(QSize(24, 24))
            return QCursor(pix)

        self.zoomInTool = QgsMapToolZoom(self.canvas, False)
        self.zoomOutTool = QgsMapToolZoom(self.canvas, True)
        self.panTool = QgsMapToolPan(self.canvas)
        self.infoTool = InfoTool(self.canvas)

        self.infoTool.setAction(self.actionInfo)
        self.zoomInTool.setAction(self.actionZoom_In)
        self.zoomOutTool.setAction(self.actionZoom_Out)
        self.panTool.setAction(self.actionPan)

        connectAction(self.actionZoom_In, self.zoomInTool)
        connectAction(self.actionZoom_Out, self.zoomOutTool)
        connectAction(self.actionPan, self.panTool)
        connectAction(self.actionInfo, self.infoTool)

        self.zoomInTool.setCursor(cursor(':/icons/in'))
        self.zoomOutTool.setCursor(cursor(':/icons/out'))
        self.infoTool.setCursor(cursor(':/icons/select'))

        self.actionRaster.triggered.connect(self.toggle_raster_layers)
        self.actionHome.triggered.connect(self.homeview)

    def homeview(self):
        """
        Zoom the mapview canvas to the extents the project was opened at i.e. the
        default extent.
        """
        if self.defaultextent:
            self.canvas.setExtent(self.defaultextent)
            self.canvas.refresh()

    def form_valid_for_capture(self, form):
        """
        Check if the given form is valid for capture.
        :param form: The form to check.
        :return: True if valid form for capture
        """
        return form.has_geometry and self.project.layer_can_capture(form.QGISLayer)

    def first_capture_form(self):
        """
        Return the first valid form for capture.
        """
        for form in self.project.forms:
            if self.form_valid_for_capture(form):
                return form

    def load_form(self, form):
        """
        Load the given form so it's the active one for capture
        :param form: The form to load
        """
        self.clear_capture_tools()
        self.dataentryselection.setIcon(QIcon(form.icon))
        self.dataentryselection.setText(form.icontext)
        self.create_capture_buttons(form)
        self.current_form = form

    def create_capture_buttons(self, form):
        """
        Create the capture buttons in the toolbar for the given form.
        :param form: The active form.
        """
        tool = form.getMaptool()(self.canvas, form.settings)
        for action in tool.actions:
            # Create the action here.
            if action.ismaptool:
                action.toggled.connect(partial(self.setMapTool, tool))

            # Set the action as a data entry button so we can remove it later.
            action.setProperty("dataentry", True)
            self.editgroup.addAction(action)
            self.layerbuttons.append(action)
            self.projecttoolbar.insertAction(self.topspaceraction, action)
            action.setChecked(action.isdefault)

        if hasattr(tool, 'geometryComplete'):
            add = partial(self.add_new_feature, form)
            tool.geometryComplete.connect(add)
        else:
            tool.finished.connect(self.openForm)

        tool.error.connect(self.show_invalid_geometry_message)

    def show_invalid_geometry_message(self, message) -> None:
        """
        Shows the message to the user if the there is a invalid geometry capture.
        :param message: The message to show the user.
        """
        RoamEvents.raisemessage("Invalid geometry capture", message, level=RoamEvents.CRITICAL)
        if self.canvas.currentLayer() is not None:
            self.canvas.currentLayer().rollBack()
        RoamEvents.editgeometry_invalid.emit()

    def add_new_feature(self, form, geometry: QgsGeometry):
        """
        Add a new new feature to the given layer
        :param form:  The form to use for the new feature.
        :param geometry: The new geometry to create the feature for.
        """
        # NOTE This function is doing too much, acts as add and also edit.
        layer = form.QGISLayer
        if geometry.isMultipart():
            geometry.convertToMultiType()

        # Transform the new geometry back into the map layers geometry if it's needed
        transform = self.canvas.mapSettings().layerTransform(layer)
        if transform.isValid():
            geometry.transform(transform, QgsCoordinateTransform.ReverseTransform)

        try:
            form, feature = self.editfeaturestack.pop()
            self.editfeaturegeometry(form, feature, newgeometry=geometry)
            return
        except IndexError:
            pass

        feature = form.new_feature(geometry=geometry)
        RoamEvents.load_feature_form(form, feature, editmode=False)

    def editfeaturegeometry(self, form, feature, newgeometry):
        # TODO Extract into function.
        layer = form.QGISLayer
        layer.startEditing()
        feature.setGeometry(newgeometry)
        layer.updateFeature(feature)
        saved = layer.commitChanges()
        if not saved:
            map(roam.utils.error, layer.commitErrors())
        self.canvas.refresh()
        self.currentfeatureband.setToGeometry(feature.geometry(), layer)
        RoamEvents.editgeometry_complete.emit(form, feature)
        self.canvas.mapTool().setEditMode(False, None, None)
        self.restore_last_form()

    def clear_capture_tools(self):
        """
        Clear the capture tools from the toolbar.
        :return: True if the capture button was active at the time of clearing.
        """
        captureselected = False
        for action in self.projecttoolbar.actions():
            if action.objectName() == "capture" and action.isChecked():
                captureselected = True

            if action.property('dataentry'):
                self.projecttoolbar.removeAction(action)
        return captureselected

    def toggle_raster_layers(self) -> None:
        """
        Toggle all raster layers on or off.
        """
        # Freeze the canvas to save on UI refresh
        dlg = PickActionDialog(msg="Raster visibility")
        actions = [
            (":/icons/raster_0", "Off", partial(self._set_basemaps_opacity, 0), "photo_off"),
            (":/icons/raster_25", "25%", partial(self._set_basemaps_opacity, .25), "photo_25"),
            (":/icons/raster_50", "50%", partial(self._set_basemaps_opacity, .50), "photo_50"),
            (":/icons/raster_75", "75%", partial(self._set_basemaps_opacity, .75), "photo_75"),
            (":/icons/raster_100", "100%", partial(self._set_basemaps_opacity, 1), "photo_100"),
        ]

        # ":/icons/raster_100"), "100%", self, triggered=partial(self._set_raster_layer_value, 1),
        #                                                objectName="photo_100")
        dialog_actions = []
        for action in actions:
            icon = QIcon(action[0])
            qaction = QAction(icon, action[1], self, triggered=action[2], objectName=action[3])
            dialog_actions.append(qaction)

        dlg.addactions(dialog_actions)
        dlg.exec_()

    def _set_basemaps_opacity(self, value=0) -> None:
        """
        Set the opacity for all basemap raster layers.
        :param value: The opacity value betwen 0 and 1
        """
        tree = QgsProject.instance().layerTreeRoot()
        for node in tree.findLayers():
            layer = node.layer()
            if node.layer().type() == QgsMapLayer.RasterLayer:
                if value > 0:
                    node.setItemVisibilityChecked(Qt.Checked)
                    renderer = layer.renderer()
                    renderer.setOpacity(value)
                if value == 0:
                    node.setItemVisibilityChecked(Qt.Unchecked)

        self.canvas.refresh()

    def cleanup(self):
        """
        Clean up when the project has changed.
        :return:
        """
        # TODO Review cleanup
        # self.bridge.clear()
        self.gpsband.reset()
        self.gpsband.hide()
        self.clear_selection()
        self.clear_temp_objects()
        self.clear_capture_tools()
        for action in self.layerbuttons:
            self.editgroup.removeAction(action)
