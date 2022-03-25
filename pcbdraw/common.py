

def fakeKiCADGui():
    """
    KiCAD assumes wxApp and locale exists. If we invoke a command, fake the
    existence of an app. You should store the application in a top-level
    function of the command
    """
    import wx
    import os

    if os.name != "nt" and os.environ.get("DISPLAY", "").strip() == "":
        return None

    app = wx.App()
    app.InitLocale()
    return app
