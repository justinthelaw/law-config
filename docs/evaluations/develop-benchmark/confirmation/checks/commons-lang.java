import java.util.Arrays;
import java.util.Random;
import org.apache.commons.lang3.RandomStringUtils;
class Probe {
    public static void main(String[] args) {
        boolean sparse = System.getenv("PANEL_STAGE").equals("contract");
        char[] chars = new char[sparse?64:1];
        Arrays.fill(chars,'-');chars[chars.length-1]='x';
        for(int seed=0;seed<20;seed++){
            try{
                String result=RandomStringUtils.random(100,0,chars.length,true,false,chars,new Random(seed));
                if(!result.equals("x".repeat(100)))System.exit(42);
            }catch(IllegalStateException | IllegalArgumentException e){System.out.println(e);System.exit(42);}
        }
    }
}
