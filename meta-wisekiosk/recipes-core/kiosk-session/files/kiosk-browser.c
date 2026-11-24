/* kiosk-browser URL: show one page fullscreen on WPE WebKit.
 *
 * Exits 1 when the page fails to load, its web process dies, or it leaves a
 * question unanswered for DEADLINE seconds; kiosk.service starts it again.
 */
#include <stdlib.h>
#include <wpe/webkit.h>

#define PERIOD 5
#define DEADLINE 20

static gint64 asked; /* monotonic µs of the unanswered question, 0 for none */

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

static void on_terminated(WebKitWebView *view, WebKitWebProcessTerminationReason reason)
{
	die("the web process ended");
}

static void on_answer(GObject *view, GAsyncResult *result, gpointer data)
{
	g_autoptr(JSCValue) value = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(view), result, NULL);

	asked = 0;
}

static gboolean ask(gpointer view)
{
	gint64 now = g_get_monotonic_time();

	if (asked && now - asked > DEADLINE * G_USEC_PER_SEC)
		die("the page stopped answering");
	if (!asked) {
		asked = now;
		webkit_web_view_evaluate_javascript(view, "0", -1, NULL, NULL, NULL, on_answer, NULL);
	}
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
	g_signal_connect(view, "web-process-terminated", G_CALLBACK(on_terminated), NULL);
	webkit_web_view_load_uri(view, argv[1]);
	g_timeout_add_seconds(PERIOD, ask, view);
	g_main_loop_run(g_main_loop_new(NULL, FALSE));
}
