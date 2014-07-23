# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    This module copyright (C) 2012-2014 Therp BV (<http://therp.nl>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import os
import sys
import unohelper
import base64
import tempfile
import traceback
from com.sun.star.task import XJobExecutor

try:
    import Danny
except ImportError:
    #enable to run without extension context
    sys.path.append(os.path.join(
        os.path.dirname(__file__),
        'pythonpath',
    ))
    import Danny
import TinySocket
import FileUtils
import Localization
import LoginObject


class Merge(Localization.LocalizedObject, XJobExecutor):
    """
    Send the current open document to the OpenERP server
    and trigger an Aeroo report on resources in the
    stored selection. Merge the documents into one, separated
    by newlines on the OpenOffice side and open the document
    in the user's window.
    """

    def __init__(self, ctx):
        super(Merge, self).__init__(ctx)
        try:
            self.__init_wrapped__(ctx)
        except Exception, e:
            print >> sys.stderr, e
            traceback.print_exc(file=sys.stderr)

    def __init_wrapped__(self, ctx):

        self.ctx = ctx
        self.module = "OpenERP_Aeroo"
        self.version = "0.1"
        login = LoginObject.LoginObject(ctx).getLogin()
        if not login:
            exit(1)
        (url, database, uid, password) = login
        self.sock = TinySocket.RPCSession(ctx, url)
        Desktop = Danny.getDesktop()
        current = Desktop.getCurrentComponent()
        if not current.hasLocation():
            tempFile = tempfile.mkstemp('.odt')
            os.close(tempFile[0])
            tempURL = Danny.convertToURL(tempFile[1])
            current.storeAsURL(
                tempURL,
                Danny.Array(
                    Danny.makePropertyValue(
                        "MediaType",
                        "application/vnd.oasis.opendocument.text"))
                )
        current.store()

        dialog = ctx.getServiceManager()\
            .createInstanceWithContext(
                "com.sun.star.awt.DialogProvider", ctx)\
            .createDialog(
                "vnd.sun.star.extension://org.openerp/dialogs/"
                "FilterChooser.xdl")

        listbox = dialog.getControl('filter')

        def ir_filters(method, *args):
            return self.sock.execute(
                database, uid, password, 'ir.filters', method, *args)

        filters = {}
        for filter_data in ir_filters(
                'read',
                ir_filters(
                    'search',
                    [('user_id', 'in', [uid, False])],
                    0, 0, 'name')):
            filters.setdefault(filter_data['model_id'], [])
            filters[filter_data['model_id']].append(filter_data)

        def ir_model(method, *args):
            return self.sock.execute(
                database, uid, password, 'ir.model', method, *args)

        for model in ir_model(
                'read',
                ir_model(
                    'search',
                    [('model', 'in', filters.keys())]),
                ['name', 'model']):
            for filter_data in filters[model['model']]:
                filter_data['display_name'] = "%s (%s)" % (
                    filter_data['name'], model['name'])

        firstItem = None
        for filter_list in filters.itervalues():
            for filter_data in filter_list:
                firstItem = filter_data['display_name']
                listbox.addItem(filter_data['display_name'], '0')
        if firstItem:
            listbox.setText(firstItem)

        if dialog.execute():
            pass
        dialog.dispose()

        data = FileUtils.read_data_from_file(
            FileUtils.get_absolute_file_path(
                current.getURL()[7:]
                )
            )
        res = self.sock.execute(
            database,
            uid,
            password,
            'instant.aeroo',
            'create_report',
            base64.encodestring(data)
            )
        if res:
            if res[0]:
                # Combine files, based on
                # Russell Philip's OOO Macros
                # http://sourceforge.net/projects/ooomacros/files/ (GPL)
                tempFile = tempfile.mkstemp('.odt')
                os.close(tempFile[0])
                filename = tempFile[1]
                component = False
                for doc in res[0]:
                    if not component:
                        FileUtils.write_data_to_file(
                            filename,
                            base64.decodestring(doc)
                            )
                        component = Desktop.loadComponentFromURL(
                            Danny.convertToURL(filename),
                            "_blank", 0,
                            ()
                            )
                    else:
                        tempFile = tempfile.mkstemp('.odt')
                        os.close(tempFile[0])
                        filename2 = tempFile[1]
                        FileUtils.write_data_to_file(
                            filename2,
                            base64.decodestring(doc)
                            )
                        # Get a cursor at the end of the text
                        oTextRange = component.Text.End
                        oTextCursor = component.Text.createTextCursorByRange(
                            oTextRange)
                        # Insert page break by changing PageDescName to the
                        # existing page style name
                        oTextCursor.PageDescName = oTextCursor.PageStyleName
                        # Insert document at text cursor position
                        oTextCursor.insertDocumentFromURL(
                            Danny.convertToURL(filename2), ())
                        os.remove(filename2)
            else:
                # Second arg *may* contain a warning or error message
                Danny.ErrorDialog(self.localize("error"), "%s" % res[1])
        else:
            Danny.ErrorDialog(self.localize("error"),
                              self.localize("not.create"))

g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    Merge,
    "org.openoffice.openerp.report.aeroo.merge", ("com.sun.star.task.Job",),)


class About(Localization.LocalizedObject, XJobExecutor):
    def __init__(self, ctx):
        super(About, self).__init__(ctx)
        self.module = "OpenERP_Aeroo"
        self.version = "0.1"
        self.win = Danny.DBModalDialog(
            60, 50, 200, 215,
            self.localize("about"))

        fdBigFont = Danny.createUnoStruct("com.sun.star.awt.FontDescriptor")
        fdBigFont.Width = 20
        fdBigFont.Height = 25
        fdBigFont.Weight = 120
        fdBigFont.Family = 3

        oLabelProdDesc = self.win.addFixedText("lblProdDesc", 3, 30, 196, 175)
        oLabelProdDesc.Model.TextColor = 1
        fdBigFont.Width = 10
        fdBigFont.Height = 11
        fdBigFont.Weight = 76
        oLabelProdDesc.Model.FontDescriptor = fdBigFont
        oLabelProdDesc.Model.Align = 1
        oLabelProdDesc.Model.FontRelief = 1
        oLabelProdDesc.Model.MultiLine = True
        oLabelProdDesc.Text = self.localize("content")

        self.win.doModalDialog("", None)

g_ImplementationHelper.addImplementation(
    About,
    "org.openoffice.openerp.report.aeroo.about",
    ("com.sun.star.task.Job",),)

if __name__ == "__main__":
# from https://wiki.openoffice.org/wiki/UNO_component_packaging#
# Python_component_testing
    import os
    import uno

    # Start OpenOffice.org, listen for connections and open testing document
    os.system("lowriter '--accept=socket,host=localhost,port=2002;urp;' &")

    # Get local context info
    localContext = uno.getComponentContext()
    resolver = localContext.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", localContext)

    ctx = None

    # Wait until the OO.o starts and connection is established
    while ctx is None:
        try:
            ctx = resolver.resolve(
                "uno:socket,host=localhost,port=2002;urp;"
                "StarOffice.ComponentContext")
        except:
            pass

    # Trigger our job
    merge = Merge(ctx)
