// Global hotkeys through Carbon RegisterEventHotKey, which needs no Accessibility permission.
import Carbon.HIToolbox
import Foundation

final class Hotkeys {
    private static var actions: [UInt32: () -> Void] = [:]
    private var refs: [EventHotKeyRef] = []
    private var handler: EventHandlerRef?

    // Each key code is registered with Control-Option-Command.
    init(_ bindings: [(keyCode: Int, action: () -> Void)]) {
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, event, _ in
            var id = EventHotKeyID()
            GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil,
                              MemoryLayout<EventHotKeyID>.size, nil, &id)
            Hotkeys.actions[id.id]?()
            return noErr
        }, 1, &spec, nil, &handler)
        for (index, binding) in bindings.enumerated() {
            let id = UInt32(index + 1)
            var ref: EventHotKeyRef?
            let status = RegisterEventHotKey(UInt32(binding.keyCode), UInt32(controlKey | optionKey | cmdKey),
                                             EventHotKeyID(signature: OSType(0x5049_5450), id: id), GetApplicationEventTarget(), 0, &ref)
            if status == noErr, let ref { Hotkeys.actions[id] = binding.action; refs.append(ref) }
            else { FileHandle.standardError.write("PitPat: hotkey \(binding.keyCode) unavailable (\(status))\n".data(using: .utf8)!) }
        }
    }
}
