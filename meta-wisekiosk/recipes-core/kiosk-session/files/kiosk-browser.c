/* kiosk-browser URL: show one page fullscreen on WPE WebKit.
 *
 * Exits 1 when the page fails to load or its web process ends, and pets
 * systemd's watchdog each time the page answers, so kiosk.service brings back
 * a page that stops. Its status is "loaded" once the page has loaded.
 */
#include <stdlib.h>
#include <systemd/sd-daemon.h>
#include <wpe/webkit.h>

#define PERIOD 5

static void die(const char *why)
{
	g_printerr("kiosk-browser: %s\n", why);
	exit(1);
}

static gboolean on_load_failed(WebKitWebView *view, WebKitLoadEvent event, char *uri, GError *error)
{
	die(error->message);
	return TRUE;
}

static void on_load_changed(WebKitWebView *view, WebKitLoadEvent event)
{
	if (event == WEBKIT_LOAD_FINISHED)
		sd_notify(0, "STATUS=loaded");
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

int main(int argc, char **argv)
{
	if (argc != 2)
		die("usage: kiosk-browser URL");

	WebKitSettings *settings = webkit_settings_new_with_settings("enable-developer-extras", TRUE, NULL);
	WebKitWebView *view = g_object_new(WEBKIT_TYPE_WEB_VIEW,
		"network-session", webkit_network_session_new_ephemeral(), "settings", settings, NULL);

	g_signal_connect(view, "load-failed", G_CALLBACK(on_load_failed), NULL);
	g_signal_connect(view, "load-changed", G_CALLBACK(on_load_changed), NULL);
	g_signal_connect(view, "web-process-terminated", G_CALLBACK(on_terminated), NULL);
	webkit_web_view_load_uri(view, argv[1]);
	g_timeout_add_seconds(PERIOD, ask, view);
	g_main_loop_run(g_main_loop_new(NULL, FALSE));
}
