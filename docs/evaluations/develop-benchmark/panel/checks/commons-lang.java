import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.apache.commons.lang3.concurrent.TimedSemaphore;

class Probe {
    public static void main(String[] args) throws Exception {
        if ("preserve".equals(System.getenv("PANEL_STAGE"))) {
            TimedSemaphore s = new TimedSemaphore(1, TimeUnit.DAYS, 1);
            try {
                if (!s.tryAcquire() || s.tryAcquire() || s.getAcquireCount()!=1) System.exit(42);
            } finally { s.shutdown(); }
            return;
        }
        Object builder;
        try { builder = TimedSemaphore.class.getMethod("builder").invoke(null); }
        catch (NoSuchMethodException absent) { System.out.println("no public builder"); System.exit(42); return; }
        Class<?> b=builder.getClass();
        for (Object[] call : new Object[][] {{"setFair",boolean.class,true},{"setLimit",int.class,1},
                {"setPeriod",long.class,2L},{"setTimeUnit",TimeUnit.class,TimeUnit.SECONDS}}) {
            try { b.getMethod((String)call[0], (Class<?>)call[1]).invoke(builder, call[2]); }
            catch (NoSuchMethodException absent) { System.out.println("missing public " + call[0]); System.exit(42); }
        }
        TimedSemaphore s=(TimedSemaphore)b.getMethod("get").invoke(builder);
        List<Integer> order=Collections.synchronizedList(new ArrayList<>());
        List<Thread> threads=new ArrayList<>();
        try {
            s.acquire();
            for(int id=0;id<3;id++) {
                final int n=id;
                Thread t=new Thread(()->{try {s.acquire();order.add(n);} catch(InterruptedException ignored) {}});
                t.setDaemon(true); threads.add(t);t.start();
                long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);
                while(t.getState()!=Thread.State.WAITING && t.getState()!=Thread.State.TIMED_WAITING
                       && System.nanoTime()<until) Thread.sleep(2);
                if(t.getState()!=Thread.State.WAITING && t.getState()!=Thread.State.TIMED_WAITING)
                    throw new IllegalStateException("test could not establish a blocked caller");
            }
            threads.get(1).interrupt(); threads.get(1).join(2000);
            for(int expected=0;expected<2;expected++) {
                long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(6);
                while(order.size()<=expected && System.nanoTime()<until) Thread.sleep(2);
            }
            System.out.println("FIFO arrivals after interrupted waiter: "+order);
            if(!order.equals(List.of(0,2))) System.exit(42);
        } finally {s.shutdown();for(Thread t:threads)t.interrupt();}
    }
}
