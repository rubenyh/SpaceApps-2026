import SwiftUI

struct ReadingsView: View {
    let baseURL: String
    let astronautID: String
    let vitals: String
    @State private var status: Status?
    @State private var lastOK: Date?
    @State private var offline = false

    var body: some View {
        List {
            Label(vitals, systemImage: "heart").font(.footnote)
            if offline {
                Text(lastOK == nil ? "Sin conexión" : "Sin conexión · datos de \(Labels.clock(lastOK))")
                    .font(.footnote)
                    .foregroundStyle(.orange)
            } else if status == nil {
                ProgressView()
            }
            ForEach(status?.sensors ?? []) { s in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(Labels.name(s.kind)).font(.caption)
                        Spacer()
                        Text(Labels.state(s.status))
                            .font(.caption2.bold())
                            .foregroundStyle(s.status == "alert" ? .red : .yellow)
                    }
                    Text(Labels.value(s.latest)).font(.title3)
                    if let r = s.latest {
                        Text("\(Labels.clock(r.recordedAt)) · \(Labels.age(s.ageSeconds))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .accessibilityElement(children: .combine)
            }
        }
        .task(id: baseURL + astronautID) {
            while !Task.isCancelled {
                do {
                    status = try await Api.get(baseURL, "/astronauts/\(astronautID)/status")
                    lastOK = Date()
                    offline = false
                } catch {
                    offline = true // keep the last data on screen
                }
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }
}
