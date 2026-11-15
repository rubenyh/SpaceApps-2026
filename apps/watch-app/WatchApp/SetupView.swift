import SwiftUI

struct SetupView: View {
    @AppStorage("baseURL") private var baseURL = ""
    @AppStorage("astronautID") private var astronautID = ""
    @State private var draft = ""
    @State private var astronauts: [Astronaut] = []
    @State private var error: String?

    var body: some View {
        List {
            TextField("http://IP:8000", text: $draft)
                .textContentType(.URL)
            Button("Cargar astronautas") { Task { await load() } }
            if let error { Text(error).font(.footnote).foregroundStyle(.red) }
            ForEach(astronauts) { a in
                Button {
                    // Saved together, so the root never sees a URL without an astronaut.
                    baseURL = cleaned
                    astronautID = a.id
                } label: {
                    Label(a.displayName, systemImage: a.id == astronautID ? "checkmark" : "person")
                }
            }
        }
        .navigationTitle("Ajustes")
        .onAppear { if draft.isEmpty { draft = baseURL } }
    }

    private var cleaned: String {
        var s = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }

    private func load() async {
        guard let url = URL(string: cleaned), url.scheme == "http" || url.scheme == "https", url.host != nil else {
            error = "URL inválida"
            return
        }
        do {
            astronauts = try await Api.get(cleaned, "/astronauts")
            error = astronauts.isEmpty ? "Sin astronautas" : nil
        } catch {
            self.error = "Sin conexión"
        }
    }
}
