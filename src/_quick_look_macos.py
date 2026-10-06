"""Native Quick Look, loaded lazily by quick_look only on macOS.

Insert a dedicated NSResponder into the Qt window's native responder chain.
Quick Look itself calls begin/endPreviewPanelControl; only its current controller
may alter the panel's data source. All calls run on the Qt/Cocoa GUI thread.
"""
import ctypes
import weakref
import objc
from AppKit import (NSResponder, NSView, NSEventTypeKeyDown,
                    NSEventModifierFlagShift, NSEventModifierFlagControl,
                    NSEventModifierFlagOption, NSEventModifierFlagCommand)
from Foundation import NSURL
from Quartz import QLPreviewPanel
from PyQt6.QtWidgets import QApplication


class MahoganyPreviewResponder(NSResponder, protocols=[
        objc.protocolNamed('QLPreviewPanelDataSource'),
        objc.protocolNamed('QLPreviewPanelDelegate')]):
    @objc.signature(objc._C_NSBOOL + b'@:@')
    def acceptsPreviewPanelControl_(self, panel):
        return self.session is not None and self.session.url is not None

    def beginPreviewPanelControl_(self, panel):
        panel.setDataSource_(self)
        panel.setDelegate_(self)

    def endPreviewPanelControl_(self, panel):
        if panel.dataSource() == self:
            panel.setDataSource_(None)
        if panel.delegate() == self:
            panel.setDelegate_(None)

    def numberOfPreviewItemsInPreviewPanel_(self, panel):
        return int(self.session is not None and self.session.url is not None)

    def previewPanel_previewItemAtIndex_(self, panel, index):
        return self.session.url if self.session is not None and index == 0 else None

    def previewPanel_handleEvent_(self, panel, event):
        if self.session is None or event.type() != NSEventTypeKeyDown:
            return False
        key = event.charactersIgnoringModifiers()
        if key == ' ':
            self.session.close()
            return True
        if key in ('\uf700', '\uf701'):
            modifiers = (NSEventModifierFlagShift | NSEventModifierFlagControl |
                         NSEventModifierFlagOption | NSEventModifierFlagCommand)
            if event.modifierFlags() & modifiers:
                return False
            import quick_look
            owner = self.session.owner()
            return owner is not None and quick_look.navigate_preview(owner, -1 if key == '\uf700' else 1)
        return False


class NativePreview:
    def __init__(self, owner):
        if QApplication.platformName() != 'cocoa':
            raise RuntimeError('Native Quick Look requires the Cocoa Qt platform')
        self.owner = weakref.ref(owner)
        self.view = objc.objc_object(c_void_p=ctypes.c_void_p(int(owner.winId())))
        if not self.view.isKindOfClass_(NSView):
            raise RuntimeError('Qt did not provide a native NSView')
        self.controller = MahoganyPreviewResponder.alloc().init()
        self.controller.session = self
        self.previous = None
        self.attached = False
        self.url = None
        self.path = None
        self.panel = None

    def show(self, path):
        self.controller.session = self
        panel = QLPreviewPanel.sharedPreviewPanel()
        if self.panel == panel and panel.isVisible() and self.path == path:
            self.close()
            return
        self.url = NSURL.fileURLWithPath_(path)
        self.path = path
        self.panel = panel
        if not self.attached:
            self.previous = self.view.nextResponder()
            self.controller.setNextResponder_(self.previous)
            self.view.setNextResponder_(self.controller)
            self.attached = True
        window = self.view.window()
        window.makeKeyAndOrderFront_(None)
        panel.setWorksWhenModal_(True)
        # Showing the panel initiates Cocoa's controller handoff. A hidden
        # shared panel can still have no controller despite updateController.
        panel.makeKeyAndOrderFront_(None)
        panel.updateController()
        if panel.currentController() != self.controller:
            raise RuntimeError('Quick Look did not accept the window controller')
        if panel.dataSource() != self.controller:
            panel.setDataSource_(self.controller)
            panel.setDelegate_(self.controller)
        panel.reloadData()
        panel.setCurrentPreviewItemIndex_(0)
        panel.makeKeyAndOrderFront_(None)

    def is_open(self):
        return (self.panel is not None and self.panel.isVisible()
                and self.panel.currentController() == self.controller)

    def navigate(self, direction):
        owner = self.owner()
        if owner is None or not self.is_open():
            return
        path = owner._navigate_quick_look(direction, self.path)
        if path is None:
            return
        self.url = NSURL.fileURLWithPath_(path)
        self.path = path
        self.panel.reloadData()
        self.panel.setCurrentPreviewItemIndex_(0)

    def close(self):
        panel = self.panel
        if panel is not None and panel.currentController() in (None, self.controller):
            panel.orderOut_(None)
        self.url = None
        self.path = None
        if self.attached:
            if self.view.nextResponder() == self.controller:
                self.view.setNextResponder_(self.previous)
            self.controller.setNextResponder_(None)
            self.previous = None
            self.attached = False
        if panel is not None and panel.currentController() == self.controller:
            panel.updateController()
        self.panel = None
        self.controller.session = None
        owner = self.owner()
        if owner is not None and owner.isVisible():
            owner.activateWindow()
