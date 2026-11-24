/* kiosk-browser URL: show one page fullscreen on WPE WebKit.
 *
 * Runs the page only while vt1 is in front: it waits, petting systemd's
 * watchdog, until vt1 is, and exits 0 when another console is switched to,
 * leaving the panel to that console. A page that fails to load is tried again
 * every PERIOD seconds, with the error as the status; the first failure since
 * a page last loaded is logged. It exits 1 when its web process ends, and pets
 * the watchdog each time the page answers, so kiosk.service brings back a page
 * that stops, or one that cannot answer within the watchdog's time from the start. Its status is "loaded" and the page's title once the page has
 * loaded.
 */
#include <fcntl.h>
#include <glib-unix.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <systemd/sd-daemon.h>
#include <wpe/webkit.h>

#define PERIOD 5

static const char *url;
/* the load under way failed or was cancelled */
static gboolean failed;
/* a failure has been logged since a page last loaded */
static gboolean logged;

static void die(const char *why)
{
	g_printerr("kiosk-browser: %s\n", why);
	exit(1);
}

static gboolean load(gpointer view)
{
	webkit_web_view_load_uri(view, url);
	return G_SOURCE_REMOVE;
}

static gboolean on_load_failed(WebKitWebView *view, WebKitLoadEvent event, char *uri, GError *error)
{
	failed = TRUE;
	if (g_error_matches(error, WEBKIT_NETWORK_ERROR, WEBKIT_NETWORK_ERROR_CANCELLED))
		return FALSE;
	if (!logged)
		g_printerr("kiosk-browser: load of %s failed: %s, retrying every %d s\n", uri, error->message, PERIOD);
	logged = TRUE;
	sd_notifyf(0, "STATUS=load failed: %s", error->message);
	g_timeout_add_seconds(PERIOD, load, view);
	return FALSE;
}

/* A load that failed is FINISHED too, with the last page's title still set. */
static void on_load_changed(WebKitWebView *view, WebKitLoadEvent event)
{
	const char *title = webkit_web_view_get_title(view);

	if (event == WEBKIT_LOAD_STARTED)
		failed = FALSE;
	if (event == WEBKIT_LOAD_FINISHED && !failed && title && *title) {
		logged = FALSE;
		sd_notifyf(0, "STATUS=loaded %s", title);
	}
}

static void on_terminated(WebKitWebView *view, WebKitWebProcessTerminationReason reason)
{
	die("the web process ended");
}

static void on_answer(GObject *view, GAsyncResult *result, gpointer data)
{
	g_autoptr(JSCValue) answer = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(view), result, NULL);

	if (answer)
		sd_notify(0, "WATCHDOG=1");
}

static gboolean ask(gpointer view)
{
	webkit_web_view_evaluate_javascript(view, "0", -1, NULL, NULL, NULL, on_answer, NULL);
	return G_SOURCE_CONTINUE;
}

/* Reading the file from its start is what arms the next poll for a switch.
 * A file that cannot be read counts as vt1, so the page is shown. */
static gboolean on_vt1(int active)
{
	char name[16];
	ssize_t length = pread(active, name, sizeof name, 0);

	return length < 0 || (length == 5 && !memcmp(name, "tty1\n", 5));
}

static gboolean on_switch(int active, GIOCondition condition, gpointer data)
{
	if (!on_vt1(active))
		exit(0);
	return G_SOURCE_CONTINUE;
}

int main(int argc, char **argv)
{
	if (argc != 2)
		die("usage: kiosk-browser URL");
	url = argv[1];

	int active = open("/sys/class/tty/tty0/active", O_RDONLY | O_CLOEXEC);
	while (!on_vt1(active)) {
		poll(&(struct pollfd){ .fd = active, .events = POLLPRI }, 1, PERIOD * 1000);
		sd_notify(0, "WATCHDOG=1");
	}

	WebKitSettings *settings = webkit_settings_new_with_settings("enable-developer-extras", TRUE, NULL);
	/* Repaint the whole frame, not only its damaged parts. */
	g_autoptr(WebKitFeatureList) features = webkit_settings_get_all_features();
	WebKitFeature *damage = webkit_feature_list_find(features, "PropagateDamagingInformation");

	if (!damage)
		die("this WebKit has no PropagateDamagingInformation");
	webkit_settings_set_feature_enabled(settings, damage, FALSE);
	WebKitWebView *view = g_object_new(WEBKIT_TYPE_WEB_VIEW,
		"network-session", webkit_network_session_new_ephemeral(), "settings", settings, NULL);

	g_signal_connect(view, "load-failed", G_CALLBACK(on_load_failed), NULL);
	g_signal_connect(view, "load-changed", G_CALLBACK(on_load_changed), NULL);
	g_signal_connect(view, "web-process-terminated", G_CALLBACK(on_terminated), NULL);
	load(view);
	g_timeout_add_seconds(PERIOD, ask, view);
	g_unix_fd_add(active, G_IO_PRI, on_switch, NULL);
	g_main_loop_run(g_main_loop_new(NULL, FALSE));
}
