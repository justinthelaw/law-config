use std::cell::Cell;
use std::rc::Rc;
use tokio::sync::SetOnce;

#[test]
fn empty_mutable_borrow_does_not_initialize() {
    let mut cell = SetOnce::<String>::new();
    let exclusive: for<'a> fn(&'a mut SetOnce<String>) -> Option<&'a mut String> = SetOnce::get_mut;
    assert!(exclusive(&mut cell).is_none());
    assert!(exclusive(&mut cell).is_none());
    assert!(cell.get().is_none());
    assert!(!cell.initialized());
    assert!(cell.into_inner().is_none());
}

#[test]
fn mutations_are_visible_and_the_value_is_still_set_once() {
    let mut cell = SetOnce::new();
    assert!(cell.get_mut().is_none());
    cell.set(String::from("alpha")).unwrap();
    let pointer = cell.get().unwrap() as *const String;
    let slot = cell.get_mut().expect("initialized value");
    assert_eq!(pointer, std::ptr::from_ref(slot));
    slot.push_str("-beta");
    assert_eq!(cell.get().map(String::as_str), Some("alpha-beta"));
    assert!(cell.initialized());
    assert!(cell.set(String::from("replacement")).is_err());
    assert_eq!(cell.into_inner().as_deref(), Some("alpha-beta"));
}

#[tokio::test]
async fn existing_wait_observes_preinitialized_mutation() {
    let mut cell = SetOnce::new_with(Some(vec![3, 1]));
    cell.get_mut().expect("preinitialized value").push(4);
    assert_eq!(cell.wait().await.as_slice(), &[3, 1, 4]);
    assert_eq!(cell.into_inner().unwrap(), vec![3, 1, 4]);
}

#[test]
fn non_clone_non_send_value_is_owned_and_dropped_once() {
    struct Value { count: Rc<Cell<usize>>, sequence: usize }
    impl Drop for Value { fn drop(&mut self) { self.count.set(self.count.get() + 1); } }
    let count = Rc::new(Cell::new(0));
    {
        let mut cell = SetOnce::from(Value { count: Rc::clone(&count), sequence: 0 });
        cell.get_mut().unwrap().sequence += 1;
        assert_eq!(cell.get().unwrap().sequence, 1);
        assert_eq!(count.get(), 0);
        let owned = cell.into_inner().unwrap();
        assert_eq!(owned.sequence, 1);
        assert_eq!(count.get(), 0);
        drop(owned);
    }
    assert_eq!(count.get(), 1);
    {
        let mut cell = SetOnce::from(Value { count: Rc::clone(&count), sequence: 7 });
        cell.get_mut().unwrap().sequence += 1;
    }
    assert_eq!(count.get(), 2);
}
