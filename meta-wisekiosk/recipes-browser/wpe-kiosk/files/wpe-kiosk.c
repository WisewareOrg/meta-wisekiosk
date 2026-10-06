/* Load one URL fullscreen through WebKit's WPE Platform DRM backend.
 *
 *   wpe-kiosk URL
 *
 * Connects the default DRM device and prints one stderr line,
 * "WPP|display=<type> mode=<w>x<h>@<mHz> scale=<scale>", from the view's
 * screen: logical size, refresh rate in milli-Hertz, and the logical-to-device
 * scale. The DRM toplevel is always fullscreen.
 *
 * Environment:
 *   WPE_KIOSK_SCRIPT=PATH   evaluate PATH in the main frame each time a load
 *                           finishes, reading it then, and print each title
 *                           change to stdout as "TITLE <title>"
 *   WPE_KIOSK_FEATURES=LIST comma list of WebKit feature identifiers,
 *                           as cog's --features: case-insensitive; '-' or '!'
 *                           disables, '+' or no prefix enables, applied in
 *                           order; prints "WPP|feature <identifier>=<0|1>"
 *                           per entry, the state after all are applied
 *   WPE_KIOSK_CONSOLE=1     write console messages to stdout
 *   WPE_KIOSK_INSPECTOR=1   enable developer extras; WebKit serves the remote
 *                           inspector at WEBKIT_INSPECTOR_HTTP_SERVER when set
 *   WPE_KIOSK_MODE=WxH      before connecting, SetCrtc the first connected
 *                           connector's first WxH mode, print "WPP|preset=WxH
 *                           crtc=<id> connector=<id>", drop master, keep fd open
 *
 * SIGTERM exits 0. A connect failure, a missing view, an unknown feature or a
 * failed mode preset exits 1 with the reason on stderr; a missing URL exits 2.
 */
#include <fcntl.h>
#include <glib-unix.h>
#include <stdio.h>
#include <stdlib.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <wpe/drm/wpe-drm.h>
#include <wpe/webkit.h>

static void on_title_changed(WebKitWebView *web_view)
{
    g_print("TITLE %s\n", webkit_web_view_get_title(web_view) ?: "");
    fflush(stdout);
}

static void on_load_changed(WebKitWebView *web_view, WebKitLoadEvent event, const char *path)
{
    if (event != WEBKIT_LOAD_FINISHED)
        return;

    g_autofree char *source = NULL;
    g_autoptr(GError) error = NULL;
    if (!g_file_get_contents(path, &source, NULL, &error)) {
        g_warning("Cannot read user script %s: %s", path, error->message);
        return;
    }
    webkit_web_view_evaluate_javascript(web_view, source, -1, NULL, NULL, NULL, NULL, NULL);
}

static gboolean apply_features(WebKitSettings *settings, const char *list)
{
    g_autoptr(WebKitFeatureList) features = webkit_settings_get_all_features();
    g_auto(GStrv) items = g_strsplit(list, ",", -1);
    g_autoptr(GPtrArray) applied = g_ptr_array_new();
    for (gsize i = 0; items[i]; i++) {
        char *item = g_strchomp(items[i]);
        gboolean enabled = TRUE;
        if (item[0] == '-' || item[0] == '!') {
            enabled = FALSE;
            item++;
        } else if (item[0] == '+')
            item++;
        if (item[0] == '\0') {
            g_printerr("empty feature name in WPE_KIOSK_FEATURES\n");
            return FALSE;
        }

        WebKitFeature *feature = NULL;
        for (gsize j = 0; !feature && j < webkit_feature_list_get_length(features); j++) {
            WebKitFeature *f = webkit_feature_list_get(features, j);
            if (!g_ascii_strcasecmp(item, webkit_feature_get_identifier(f)))
                feature = f;
        }
        if (!feature) {
            g_printerr("feature '%s' is not available\n", item);
            return FALSE;
        }
        webkit_settings_set_feature_enabled(settings, feature, enabled);
        g_ptr_array_add(applied, feature);
    }
    for (guint i = 0; i < applied->len; i++) {
        WebKitFeature *f = g_ptr_array_index(applied, i);
        g_printerr("WPP|feature %s=%d\n", webkit_feature_get_identifier(f), webkit_settings_get_feature_enabled(settings, f));
    }
    return TRUE;
}

static gboolean preset_mode(const char *spec)
{
    unsigned w, h;
    char end;
    int fd = -1;
    drmModeRes *res = NULL;
    /* WPE's default device: the first card with CRTCs, connectors and encoders. */
    for (int i = 0; fd < 0 && i < 16; i++) {
        g_autofree char *path = g_strdup_printf("/dev/dri/card%d", i);
        if ((fd = open(path, O_RDWR | O_CLOEXEC)) < 0)
            continue;
        res = drmModeGetResources(fd);
        if (!res || !res->count_crtcs || !res->count_connectors || !res->count_encoders) {
            drmModeFreeResources(res);
            close(fd);
            fd = -1;
        }
    }
    if (sscanf(spec, "%ux%u%c", &w, &h, &end) != 2 || fd < 0) {
        g_printerr("mode preset: WPE_KIOSK_MODE '%s' is not WxH, or no DRM card has KMS\n", spec);
        return FALSE;
    }
    for (int i = 0; i < res->count_connectors; i++) {
        drmModeConnector *conn = drmModeGetConnector(fd, res->connectors[i]);
        if (!conn || conn->connection != DRM_MODE_CONNECTED || conn->connector_type == DRM_MODE_CONNECTOR_WRITEBACK)
            continue;
        drmModeEncoder *enc = drmModeGetEncoder(fd, conn->encoder_id);
        drmModeModeInfo *mode = NULL;
        for (int m = 0; !mode && m < conn->count_modes; m++)
            if (conn->modes[m].hdisplay == w && conn->modes[m].vdisplay == h)
                mode = &conn->modes[m];
        uint32_t handle, pitch, fb;
        uint64_t size;
        if (!enc || !enc->crtc_id || !mode || drmModeCreateDumbBuffer(fd, w, h, 32, 0, &handle, &pitch, &size)
            || drmModeAddFB(fd, w, h, 24, 32, pitch, handle, &fb)
            || drmModeSetCrtc(fd, enc->crtc_id, fb, 0, 0, &conn->connector_id, 1, mode)) {
            g_printerr("mode preset: no CRTC, no %ux%u mode, or SetCrtc failed\n", w, h);
            return FALSE;
        }
        g_printerr("WPP|preset=%ux%u crtc=%u connector=%u\n", w, h, enc->crtc_id, conn->connector_id);
        drmDropMaster(fd);
        return TRUE;
    }
    g_printerr("mode preset: no connected connector\n");
    return FALSE;
}

static gboolean on_sigterm(gpointer loop)
{
    g_main_loop_quit(loop);
    return G_SOURCE_REMOVE;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        g_printerr("usage: %s URL\n", argv[0]);
        return 2;
    }

    const char *mode = g_getenv("WPE_KIOSK_MODE");
    if (mode && !preset_mode(mode))
        return 1;

    g_autoptr(WPEDisplay) display = wpe_display_drm_new();
    g_autoptr(GError) error = NULL;
    if (!wpe_display_drm_connect(WPE_DISPLAY_DRM(display), NULL, &error)) {
        g_printerr("DRM display connect failed: %s\n", error->message);
        return 1;
    }

    g_autoptr(WebKitSettings) settings = webkit_settings_new();
    const char *features = g_getenv("WPE_KIOSK_FEATURES");
    if (features && !apply_features(settings, features))
        return 1;
    if (!g_strcmp0(g_getenv("WPE_KIOSK_CONSOLE"), "1"))
        webkit_settings_set_enable_write_console_messages_to_stdout(settings, TRUE);
    if (!g_strcmp0(g_getenv("WPE_KIOSK_INSPECTOR"), "1"))
        webkit_settings_set_enable_developer_extras(settings, TRUE);

    WebKitWebView *web_view = g_object_new(WEBKIT_TYPE_WEB_VIEW, "display", display, "settings", settings, NULL);
    WPEView *view = webkit_web_view_get_wpe_view(web_view);
    if (!view) {
        g_printerr("DRM display created no view\n");
        return 1;
    }

    WPEScreen *screen = wpe_view_get_screen(view);
    if (screen)
        g_printerr("WPP|display=%s mode=%dx%d@%d scale=%g\n", G_OBJECT_TYPE_NAME(display), wpe_screen_get_width(screen),
                   wpe_screen_get_height(screen), wpe_screen_get_refresh_rate(screen), wpe_screen_get_scale(screen));
    else
        g_printerr("WPP|display=%s\n", G_OBJECT_TYPE_NAME(display));

    const char *script = g_getenv("WPE_KIOSK_SCRIPT");
    if (script) {
        g_signal_connect(web_view, "load-changed", G_CALLBACK(on_load_changed), (gpointer) script);
        g_signal_connect(web_view, "notify::title", G_CALLBACK(on_title_changed), NULL);
    }

    g_autoptr(GMainLoop) loop = g_main_loop_new(NULL, FALSE);
    g_unix_signal_add(SIGTERM, on_sigterm, loop);
    webkit_web_view_load_uri(web_view, argv[1]);
    g_main_loop_run(loop);
    g_object_unref(web_view);
    return 0;
}
