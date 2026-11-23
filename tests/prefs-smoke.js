import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const root = GLib.getenv('XDG_DATA_HOME');
const path = `${root}/gnome-shell/extensions/break-timer@local`;
Gio.Resource.load('/usr/share/gnome-shell/org.gnome.Shell.Extensions.src.gresource')._register();
const {default: Preferences} = await import(`file://${path}/prefs.js`);
const [, bytes] = GLib.file_get_contents(`${path}/metadata.json`);
const metadata = JSON.parse(new TextDecoder().decode(bytes));
metadata.path = path;
metadata.dir = Gio.File.new_for_path(path);
const prefs = new Preferences(metadata);
const app = new Adw.Application({application_id: 'local.breaktimer.PrefsTest'});
let failure = null;

function descendants(widget) {
    const result = [widget];
    for (let child = widget.get_first_child(); child; child = child.get_next_sibling())
        result.push(...descendants(child));
    return result;
}

app.connect('activate', () => {
    try {
        const window = new Adw.PreferencesWindow({application: app});
        prefs.fillPreferencesWindow(window);
        window.present();
        const widgets = descendants(window);
        const spins = widgets.filter(w => w instanceof Adw.SpinRow);
        const entry = widgets.find(w => w instanceof Adw.EntryRow);
        if (spins.length !== 4 || !entry)
            throw new Error('Preferences controls missing');
        const settings = window._settings;
        spins[0].value = 25;
        if (settings.get_int('work-minutes') !== 25)
            throw new Error('Duration setting was not saved');
        entry.text = '22:00-08:00, 12:00-13:00';
        entry.emit('apply');
        if (settings.get_strv('blocked-ranges').length !== 2)
            throw new Error('Valid schedule was not applied');
        entry.text = '25:00-08:00';
        entry.emit('apply');
        if (!entry.has_css_class('error') || settings.get_strv('blocked-ranges').length !== 2)
            throw new Error('Invalid schedule changed settings');
        settings.set_strv('blocked-ranges', []);
        print('PASS GTK preferences render, save settings and reject invalid input');
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 800, () => {
            window.close();
            app.quit();
            return GLib.SOURCE_REMOVE;
        });
    } catch (error) {
        failure = error;
        app.quit();
    }
});
app.run([]);
if (failure)
    throw failure;
