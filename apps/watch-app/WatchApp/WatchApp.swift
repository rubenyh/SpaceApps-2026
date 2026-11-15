import SwiftUI
import WatchKit

@main
struct WatchApp: App {
    var body: some Scene {
        WindowGroup { RootView() }
    }
}

struct RootView: View {
    @AppStorage("baseURL") private var baseURL = ""
    @AppStorage("astronautID") private var astronautID = ""
    @State private var sos = SOSSender()
    @State private var banner: String?

    var body: some View {
        if baseURL.isEmpty || astronautID.isEmpty {
            SetupView()
        } else {
            TabView {
                ReadingsView(baseURL: baseURL, astronautID: astronautID)
                SOSView(sender: sos, baseURL: baseURL, astronautID: astronautID)
                SetupView()
            }
            .tabViewStyle(.verticalPage)
            .overlay(alignment: .top) {
                if let banner {
                    Button { self.banner = nil } label: {
                        Text("SOS · \(banner)").bold().frame(maxWidth: .infinity)
                    }
                    .tint(.red)
                    .buttonStyle(.borderedProminent)
                    .accessibilityHint("Toca para cerrar")
                }
            }
            .task(id: baseURL + astronautID) {
                sos.resume(baseURL: baseURL, astronautID: astronautID)
                await watchIncidents()
            }
        }
    }

    // shortcut: polling only works while the app is open, upgrade to APNs push when there is a cloud relay.
    private func watchIncidents() async {
        var known: Set<String>?
        var names: [String: String] = [:]
        while !Task.isCancelled {
            if names.isEmpty, let list = try? await Api.get(baseURL, "/astronauts", as: [Astronaut].self) {
                names = Dictionary(list.map { ($0.id, $0.displayName) }, uniquingKeysWith: { a, _ in a })
            }
            if let open = try? await Api.get(baseURL, "/incidents?status=open", as: [Incident].self) {
                // First load only seeds the known ids, so old incidents never alert.
                if let seen = known,
                   let fresh = open.first(where: { !seen.contains($0.id) && $0.astronautId != astronautID }) {
                    WKInterfaceDevice.current().play(.notification)
                    banner = names[fresh.astronautId] ?? fresh.astronautId
                }
                known = (known ?? []).union(open.map(\.id))
            }
            try? await Task.sleep(for: .seconds(5))
        }
    }
}
