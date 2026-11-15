import SwiftUI
import WatchKit

@Observable @MainActor
final class SOSSender {
    enum State { case idle, sending, sent(Date), retrying }
    private(set) var state = State.idle
    private var task: Task<Void, Never>?
    private static let pendingKey = "sosPending"

    // Retrying is safe: the server reuses the open incident.
    func send(baseURL: String, astronautID: String) {
        UserDefaults.standard.set(true, forKey: Self.pendingKey)
        guard task == nil else { return }
        state = .sending
        task = Task {
            while true {
                do {
                    try await Api.sos(baseURL, astronautID: astronautID)
                    break
                } catch {
                    state = .retrying
                    try? await Task.sleep(for: .seconds(5))
                }
            }
            UserDefaults.standard.set(false, forKey: Self.pendingKey)
            state = .sent(Date())
            task = nil
        }
    }

    func resume(baseURL: String, astronautID: String) {
        if UserDefaults.standard.bool(forKey: Self.pendingKey) { send(baseURL: baseURL, astronautID: astronautID) }
    }

    var label: String {
        switch state {
        case .idle: return "Mantén 2 s para enviar"
        case .sending: return "Enviando…"
        case .sent(let at): return "Enviado \(Labels.clock(at))"
        case .retrying: return "Sin conexión, reintentando"
        }
    }
}

struct SOSView: View {
    let sender: SOSSender
    let baseURL: String
    let astronautID: String

    var body: some View {
        VStack(spacing: 8) {
            Circle()
                .fill(.red)
                .overlay(Text("SOS").font(.system(size: 40, weight: .heavy)).foregroundStyle(.white))
                .onLongPressGesture(minimumDuration: 2) { trigger() }
                .accessibilityElement()
                .accessibilityLabel("SOS")
                .accessibilityHint("Mantén pulsado 2 segundos")
                .accessibilityAction(named: "Enviar SOS") { trigger() }
            Text(sender.label).font(.footnote).multilineTextAlignment(.center)
        }
    }

    private func trigger() {
        WKInterfaceDevice.current().play(.start)
        sender.send(baseURL: baseURL, astronautID: astronautID)
    }
}
