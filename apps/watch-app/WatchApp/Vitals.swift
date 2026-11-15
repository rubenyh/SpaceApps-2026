import Foundation
import HealthKit

/// Reads the wearer's pulse (and SpO₂ when watchOS takes one) and posts it to onboard-api `POST /readings`.
/// A workout session keeps the heart sensor sampling every few seconds and the app running with the wrist down.
@Observable @MainActor
final class Vitals: NSObject {
    private(set) var label = "Sensores apagados"
    private let store = HKHealthStore()
    private var session: HKWorkoutSession?
    private var spo2Query: HKAnchoredObjectQuery?
    private var baseURL = ""
    private var astronautID = ""
    private var queue: [[String: Any]] = []
    private var flushing = false
    private var lastHR: Double?
    private var lastHRDate: Date?
    private static let maxQueue = 720 // ~1 h of pulse; oldest dropped when full, like the device buffer

    private let hr = HKQuantityType(.heartRate)
    private let spo2 = HKQuantityType(.oxygenSaturation)

    func start(baseURL: String, astronautID: String) async {
        stop()
        self.baseURL = baseURL
        self.astronautID = astronautID
        guard HKHealthStore.isHealthDataAvailable() else { label = "Salud no disponible"; return }
        do {
            try await store.requestAuthorization(toShare: [HKWorkoutType.workoutType()], read: [hr, spo2])
            let config = HKWorkoutConfiguration()
            config.activityType = .other
            config.locationType = .indoor
            let session = try HKWorkoutSession(healthStore: store, configuration: config)
            let builder = session.associatedWorkoutBuilder()
            builder.dataSource = HKLiveWorkoutDataSource(healthStore: store, workoutConfiguration: config)
            builder.delegate = self
            self.session = session
            let now = Date()
            session.startActivity(with: now)
            try await builder.beginCollection(at: now)
            label = "Midiendo…"
        } catch {
            label = "Sin permiso de Salud"
            return
        }
        watchSpO2(since: Date())
    }

    func stop() {
        if let spo2Query { store.stop(spo2Query) }
        spo2Query = nil
        guard let session else { return }
        self.session = nil
        session.end()
        // Never save a workout into the wearer's Health app.
        session.associatedWorkoutBuilder().discardWorkout()
    }

    // SpO₂ cannot be triggered by third-party apps; watchOS writes background samples to Health.
    private func watchSpO2(since start: Date) {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: nil)
        let handler: @Sendable (HKAnchoredObjectQuery, [HKSample]?, [HKDeletedObject]?, HKQueryAnchor?, Error?) -> Void = { [weak self] _, samples, _, _, _ in
            let values = (samples as? [HKQuantitySample] ?? []).map { ($0.quantity.doubleValue(for: .percent()), $0.endDate) }
            Task { @MainActor in values.forEach { self?.enqueue("spo2", $0.0, $0.1) } }
        }
        let query = HKAnchoredObjectQuery(type: spo2, predicate: predicate, anchor: nil, limit: HKObjectQueryNoLimit, resultsHandler: handler)
        query.updateHandler = handler
        store.execute(query)
        spo2Query = query
    }

    private func enqueue(_ kind: String, _ value: Double, _ at: Date) {
        if kind == "heart_rate" {
            guard at != lastHRDate else { return } // builder repeats the latest sample across updates
            lastHR = value
            lastHRDate = at
        }
        queue.append(Api.readingBody(astronautID: astronautID, kind: kind, value: value, at: at))
        if queue.count > Self.maxQueue { queue.removeFirst(queue.count - Self.maxQueue) }
        Task { await flush() }
    }

    private func flush() async {
        guard !flushing else { return }
        flushing = true
        defer { flushing = false }
        while let body = queue.first {
            do {
                try await Api.post(baseURL, "/readings", body)
            } catch let error as ApiError where error.message.hasPrefix("HTTP 4") {
                // Rejected by the API (unknown astronaut, unit mismatch): retrying will not help.
                label = "Rechazado: \(error.message)"
            } catch {
                label = "Sin conexión, \(queue.count) en cola"
                return // retried on the next sample
            }
            queue.removeFirst()
        }
        if let lastHR { label = "Midiendo · \(Int(lastHR)) lpm" }
    }
}

extension Vitals: HKLiveWorkoutBuilderDelegate {
    nonisolated func workoutBuilder(_ builder: HKLiveWorkoutBuilder, didCollectDataOf types: Set<HKSampleType>) {
        guard types.contains(HKQuantityType(.heartRate)),
              let stats = builder.statistics(for: HKQuantityType(.heartRate)),
              let quantity = stats.mostRecentQuantity(),
              let interval = stats.mostRecentQuantityDateInterval() else { return }
        let bpm = quantity.doubleValue(for: HKUnit.count().unitDivided(by: .minute()))
        let at = interval.end
        Task { @MainActor in self.enqueue("heart_rate", bpm, at) }
    }

    nonisolated func workoutBuilderDidCollectEvent(_ builder: HKLiveWorkoutBuilder) {}
}
