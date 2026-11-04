// Main executable of PitPat Safety.app. Runs Contents/Resources/pitpat-safety as a
// child rather than exec'ing it, so this signed bundle stays the process macOS
// credits with Bluetooth use. Forwards SIGTERM (launchd and `pitpat services-stop`)
// and exits the way the child did.
//
// Opened as an app (Spotlight, Finder, the Dock), it would run a second safety process outside
// launchd that the menu bar app can't stop and that blocks the real service's lock. So when
// LaunchServices started it, it opens the menu bar app instead, which starts the services.
import Foundation

if ProcessInfo.processInfo.environment["XPC_SERVICE_NAME"]?.hasPrefix("application.") == true {
    var opener: pid_t = 0
    let words: [String] = ["open", "-b", "com.gberfield.pitpat.menubar"]
    var args = words.map { strdup($0) } + [nil]
    if posix_spawnp(&opener, "open", nil, nil, &args, environ) == 0 {
        var status: Int32 = 0
        while waitpid(opener, &status, 0) < 0 && errno == EINTR {}
        exit(status == 0 ? 0 : 1)
    }
    exit(1)
}

let script = Bundle.main.bundlePath + "/Contents/Resources/pitpat-safety"
var child: pid_t = 0
var term = sigset_t(), none = sigset_t()
sigemptyset(&term); sigemptyset(&none); sigaddset(&term, SIGTERM)
// Held until the handler can name the child; the child starts with default handling.
sigprocmask(SIG_BLOCK, &term, nil)
var attributes: posix_spawnattr_t? = nil
posix_spawnattr_init(&attributes)
posix_spawnattr_setsigmask(&attributes, &none)
posix_spawnattr_setsigdefault(&attributes, &term)
posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETSIGMASK | POSIX_SPAWN_SETSIGDEF))
var argv = ([script] + CommandLine.arguments.dropFirst()).map { strdup($0) } + [nil]
let failure = posix_spawn(&child, script, nil, &attributes, &argv, environ)
guard failure == 0 else {
    fputs("PitPat Safety: cannot start \(script): \(String(cString: strerror(failure)))\n", stderr)
    exit(1)
}
signal(SIGTERM) { _ in kill(child, SIGTERM) }
sigprocmask(SIG_SETMASK, &none, nil)
var status: Int32 = 0
while waitpid(child, &status, 0) < 0 {
    guard errno == EINTR else { exit(1) }
}
if status & 0x7f == 0 { exit((status >> 8) & 0xff) }
// Killed by a signal: die by the same one so launchd sees what the child saw.
signal(status & 0x7f, SIG_DFL)
kill(getpid(), status & 0x7f)
exit(1)
