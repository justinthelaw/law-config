use tokio::sync::SetOnce;

#[test]
fn a_shared_reference_cannot_yield_mutable_access() {
    let cell = SetOnce::from(String::from("owned"));
    let shared = &cell;
    let _ = shared.get_mut();
}
