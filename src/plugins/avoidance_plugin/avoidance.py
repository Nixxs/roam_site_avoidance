# Avoidance Plugin produced by BZ & NW - Technology One - May 2017
# Alarm1 modified from sample sourced from public domain
# Alarm2 modified from sample by user spoonsandlessspoons on freesound.org

#Avoidance Plugin modified by John de Kruijff - FMG - July 2021
#    - Added Volume variables to force unmute and set windows volume to user defined value when alarm is triggered.
#    - Method uses nircmd.exe command line functions to adjust volume controls.

#Avoidance Plugin modified by Gabby Dale - FMG - November 2021
#   - Added borderFlash function tha changes the colour of the screen border pixels when either alarm is triggered.
#   - Border flash is orange when the permit alarm (alarm == 1) and red when the abNOGO alarm (alarm == 2) are triggered.
#   - Restrict alarm enabled with border flash blue (alarm == 3) but no sound is made.

import os
import subprocess

from qgis.PyQt.QtWidgets import QWidget, QInputDialog, QLineEdit
from qgis.PyQt.QtMultimedia import QSound
from qgis.PyQt.QtCore import QThread, QTimer
from qgis.PyQt.uic import loadUiType

from roam import project
from roam.api import GPS, RoamEvents
from roam.api.plugins import Page
from qgis.core import (QgsFeature, QgsGeometry, QgsRectangle,
                       QgsVectorLayer, QgsProject,
                       QgsField, QgsCoordinateTransform,
                       QgsCoordinateReferenceSystem, QgsFeatureRequest)

from roam.editorwidgets.optionwidget import OptionWidget
from roam.editorwidgets.numberwidget import NumberWidget

def pages():
    return [AvoidancePlugin]

def resolve(name):
    f = os.path.join(os.path.dirname(__file__), name)
    return f

def valid_avoidance_settings(settings):
    try:
        settings = settings['avoidance']
        settings['permitdist']
        settings['restrictdist']
        settings['avoiddist']
        settings['volume']
        return True, settings
    except KeyError:
        return False, {}

alarmlevel = 0
def setalarmlevel(int):
    global alarmlevel
    alarmlevel = int

gpspoint = None
def setgpspoint(gpoint):
    global gpspoint
    gpspoint = gpoint

widget, base = loadUiType(resolve("ui.ui"))


class AvoidancePlugin(widget, base, Page):
    title = "Avoidance"
    icon = resolve("avoidance.png")

    def __init__(self, api, parent=None):
        api.mapwindow.gpslabelposition.setStyleSheet("font-size: 40px")
        api.mapwindow.canvas.setStyleSheet('border: 10px solid white;')
        self.project = None
        super(AvoidancePlugin, self).__init__(parent)

        self.api = api

        self.setupUi(self)
        self.initUI()

        GPS.gpsposition.connect(self.gpsposition)

        self.saveButton.pressed.connect(self.save)
        self.editButton.pressed.connect(self.edit)

        self.timer = QTimer()
        self.timer.start(1000)
        self.timer.timeout.connect(self.alarm)

    def alarm(self):
        #set volume from project config file
        maxVol = 65535
        volLvl =((float(self.volume_level_setting))/100) * maxVol
        #set file path and command for nircmd.exe
        fileDir = os.path.dirname(__file__)
        nircmdFP = fileDir +"\\nircmd.exe"
        nircmdFP = nircmdFP.replace('/','\\\\')
        setVolLevelCMD = nircmdFP +" setsysvolume "+ str(volLvl)
        setUnMuteCMD = nircmdFP +" mutesysvolume 0"
        if gpspoint is None:
            return
        setalarmlevel(self.checkLocation(gpspoint))
        if alarmlevel == 1:
            QSound(resolve("Alert1.wav")).play()
            subprocess.call(setVolLevelCMD)
            subprocess.call(setUnMuteCMD)
            self.borderFlash('orange')
        elif alarmlevel == 2:
            QSound(resolve("Alert2.wav")).play()
            subprocess.call(setVolLevelCMD)
            subprocess.call(setUnMuteCMD)
            self.borderFlash('red')
        elif alarmlevel == 3:
            self.borderFlash('blue')
        else:
            self.api.mapwindow.canvas.setStyleSheet('border: 40px solid white;')

    def borderFlash(self, color):
        if self.api.mapwindow.canvas.styleSheet() == 'border: 40px solid ' + color + ';':
            self.api.mapwindow.canvas.setStyleSheet('border: 40px solid white;')
        else:
            self.api.mapwindow.canvas.setStyleSheet('border: 40px solid ' + color + ';')

    def initUI(self):
        config = {
            "list": {
                "items": [
                    "1;On",
                    "0;Off"
                ]
            }
        }
        self.permitwrapper = OptionWidget.for_widget(self.permit_switch, layer=None, label=self.permit_label, field=None, parent=None)
        self.permitwrapper.initWidget(self.permit_switch, {})

        self.avoidwrapper = OptionWidget.for_widget(self.avoid_switch, layer=None, label=self.avoid_label, field=None, parent=None)
        self.avoidwrapper.initWidget(self.avoid_switch, {})

        self.restrictwrapper = OptionWidget.for_widget(self.restrict_switch, layer=None, label=self.restrict_label, field=None, parent=None)
        self.restrictwrapper.initWidget(self.restrict_switch, {})

        self.volumewrapper = OptionWidget.for_widget(self.volume_switch, layer=None, label=self.volume_label, field=None, parent=None)
        self.volumewrapper.initWidget(self.volume_switch, {})  

        self.permitwrapper.config = config
        self.avoidwrapper.config = config
        self.restrictwrapper.config = config
        self.volumewrapper.config = config

        self.permitwrapper2 = NumberWidget.for_widget(self.permit_distance, layer=None, label=self.permit_label, field=None, parent=None)
        self.permitwrapper2.initWidget(self.permit_distance, {})

        self.avoidwrapper2 = NumberWidget.for_widget(self.avoid_distance, layer=None, label=self.permit_label, field=None, parent=None)
        self.avoidwrapper2.initWidget(self.avoid_distance, {})

        self.restrictwrapper2 = NumberWidget.for_widget(self.restrict_distance, layer=None, label=self.permit_label, field=None, parent=None)
        self.restrictwrapper2.initWidget(self.restrict_distance, {})

        self.volumewrapper2 = NumberWidget.for_widget(self.volume_level, layer=None, label=self.volume_label, field=None, parent=None)
        self.volumewrapper2.initWidget(self.volume_level, {})

        self.permitwrapper2.config = config
        self.avoidwrapper2.config = config
        self.restrictwrapper2.config = config
        self.volumewrapper.config = config

    def save(self):
        self.permit_distance_setting = self.permitwrapper2.value()
        self.avoid_distance_setting = self.avoidwrapper2.value()
        self.restrict_distance_setting = self.restrictwrapper2.value()
        self.volume_level_setting = self.volumewrapper2.value()

        self.permit_distance_enabled = self.permitwrapper.value()
        self.avoid_distance_enabled = self.avoidwrapper.value()
        self.restrict_distance_enabled = self.restrictwrapper.value()
        self.volume_level_enabled = self.volumewrapper.value()

        self.project.save(False, False)
        self.api.mainwindow.showmap()

    def edit(self):
        password, ok = QInputDialog.getText(self, "Enter password to unlock for edit", "Password for edit:", mode=QLineEdit.Password)
        if not ok:
            return

        if password == self.settings['password']:
            self.frame.setEnabled(True)

    def project_loaded(self, project):
        self.project = project

        validformat, _ = valid_avoidance_settings(project.settings)
        if not validformat:
            RoamEvents.raisemessage("Plugin", "Invalid avoidance config.", level=1)
            return

        layers = QgsProject.instance().mapLayers().values()

        self.permitlayers = [layer for layer in layers if layer.name().startswith("permit_")]
        self.restrictlayers = [layer for layer in layers if layer.name().startswith("restrict_")]
        self.avoidlayers = [layer for layer in layers if layer.name().startswith("avoid_")]

        self.restrictwrapper.setvalue(self.restrict_distance_enabled)
        self.avoidwrapper.setvalue(self.avoid_distance_enabled)
        self.permitwrapper.setvalue(self.permit_distance_enabled)
        self.volumewrapper.setvalue(self.volume_level_enabled)

        self.permitwrapper2.setvalue(self.permit_distance_setting)
        self.avoidwrapper2.setvalue(self.avoid_distance_setting)
        self.restrictwrapper2.setvalue(self.restrict_distance_setting)
        self.volumewrapper2.setvalue(self.volume_level_setting)

    def gpsposition(self, gpoint, info):
        setgpspoint(gpoint)

    @property
    def settings(self):
        return self.project.settings.get('avoidance', {})

    @property
    def permit_distance_setting(self):
        return self.settings.get('permitdist', 0)

    @permit_distance_setting.setter
    def permit_distance_setting(self, value):
        self.settings['permitdist'] = value

    @property
    def permit_distance_enabled(self):
        return self.settings.get('permitdist_enabled', 1)

    @permit_distance_enabled.setter
    def permit_distance_enabled(self, value):
        self.settings['permitdist_enabled'] = value

    @property
    def restrict_distance_setting(self):
        return self.settings.get('restrictdist', 0)

    @restrict_distance_setting.setter
    def restrict_distance_setting(self, value):
        self.settings['restrictdist'] = value

    @property
    def restrict_distance_enabled(self):
        return self.settings.get('restrictdist_enabled', 1)

    @restrict_distance_enabled.setter
    def restrict_distance_enabled(self, value):
        self.settings['restrictdist_enabled'] = value

    @property
    def avoid_distance_setting(self):
        return self.settings.get('avoiddist', 0)

    @avoid_distance_setting.setter
    def avoid_distance_setting(self, value):
        self.settings['avoiddist'] = value

    @property
    def avoid_distance_enabled(self):
        return self.settings.get('avoiddist_enabled', 1)

    @avoid_distance_enabled.setter
    def avoid_distance_enabled(self, value):
        self.settings['avoiddist_enabled'] = value

    @property
    def volume_level_setting(self):
        return self.settings.get('volume', 0)

    @volume_level_setting.setter
    def volume_level_setting(self, value):
        self.settings['volume'] = value

    @property
    def volume_level_enabled(self):
        return self.settings.get('volume_enabled', 1)

    @volume_level_enabled.setter
    def volume_level_enabled(self, value):
        self.settings['volume_enabled'] = value
		
    def is_in_area(self, layer, distance, gpoint):
        """
        Return true if the we intersect anything on the layer.
        :param layer: The layer to check
        :param distance: The buffer distance.
        :return: True if GPS is inside a feature on the layer.
        """
        grect = QgsRectangle(gpoint.x() - distance, gpoint.y() - distance, gpoint.x() + distance, gpoint.y() + distance)

        grq = QgsFeatureRequest(grect).setFlags(QgsFeatureRequest.ExactIntersect)

        return len(list(layer.getFeatures(grq))) > 0

    def completely_inside_area(self, layer, distance, gpoint):
        """
        Return true if the gis buffer doesn't intersect 90%+ of a _permit layer
        :param layer: The layer to check
        :param distance: The buffer distance.
        :return: True if GPS is near edge of a feature on the layer
        """

        grect = QgsRectangle(gpoint.x() - distance, gpoint.y() - distance, gpoint.x() + distance, gpoint.y() + distance)
        geomrect = QgsGeometry.fromRect(grect)

        grq = QgsFeatureRequest(grect).setFlags(QgsFeatureRequest.ExactIntersect)

        #check for highest intersecting area, must be >90% of the distance squared else it is too close to an edge
        maxarea = 0
        for feat in layer.getFeatures(grq):
            part = geomrect.intersection(feat.geometry())
            #RoamEvents.raisemessage("Check Area", str(part.area()), level=1)
            if part.area() > maxarea:
                maxarea = part.area()

        return maxarea > (0.9 * float(distance ** 2) * 4)

    def checkLocation(self, gpoint):
        #if near avoidance alarm
        if self.avoid_distance_enabled:
            for layer in self.avoidlayers:
                if self.is_in_area(layer, self.avoid_distance_setting, gpoint):
                    return 2

        #if outside permit or near edge alarm
        if self.permit_distance_enabled:
            for layer in self.permitlayers:
                if self.completely_inside_area(layer, self.permit_distance_setting, gpoint):
                    #if near restrict alarm
                    if self.restrict_distance_enabled:
                        for layer in self.restrictlayers:
                            if self.is_in_area(layer, self.restrict_distance_setting, gpoint):
                                return 3
                    return 0
            return 1

        #if no issues found do not alarm
        return 0
